"""Branch-coverage tests for router schema, graph, and package internals.

Covers the strict-JSON parser/repair edge cases (no JSON, unbalanced, non-object,
schema violation, oversized, code-fence repair, section-id pattern, ranked bound),
the TOC projection cache eviction, the pipeline fallback path, and the default-LLM
construction in ``router.route``. No real Anthropic client or key is used.
"""

from __future__ import annotations

import pytest

from router.schema import (
    MAX_RANKED_ITEMS,
    MAX_RAW_RESPONSE_CHARS,
    RankedSection,
    _extract_json_object,
    parse_router_llm_json,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-based async tests on asyncio only."""
    return "asyncio"


class TestParseRouterLlmJson:
    """The OWASP-LLM01 strict-JSON boundary."""

    @pytest.mark.anyio
    async def test_valid_json_parses(self) -> None:
        """A conforming reply parses into a RawRouterLLMResponse."""
        parsed = parse_router_llm_json(
            '{"ranked_sections": [{"section_id": "sec_a1", "confidence": 0.9}],'
            ' "rationale": "matched"}'
        )
        assert parsed.ranked_sections[0].section_id == "sec_a1"
        assert parsed.rationale == "matched"

    @pytest.mark.anyio
    async def test_code_fence_is_repaired(self) -> None:
        """A reply wrapped in prose/markdown is repaired by object extraction."""
        raw = 'Here you go:\n```json\n{"ranked_sections": [], "rationale": "x"}\n```'
        parsed = parse_router_llm_json(raw)
        assert parsed.rationale == "x"

    @pytest.mark.anyio
    async def test_non_string_input_raises(self) -> None:
        """A non-text reply is rejected."""
        with pytest.raises(ValueError, match="not text"):
            parse_router_llm_json(123)  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_oversized_input_raises(self) -> None:
        """A reply over the size cap is rejected (resource-exhaustion guard)."""
        with pytest.raises(ValueError, match="exceeds maximum size"):
            parse_router_llm_json("x" * (MAX_RAW_RESPONSE_CHARS + 1))

    @pytest.mark.anyio
    async def test_non_object_json_raises(self) -> None:
        """A JSON array (not an object) is rejected."""
        with pytest.raises(ValueError, match="not an object"):
            parse_router_llm_json("[1, 2, 3]")

    @pytest.mark.anyio
    async def test_schema_violation_raises(self) -> None:
        """An out-of-range confidence fails strict schema validation."""
        with pytest.raises(ValueError, match="schema validation"):
            parse_router_llm_json(
                '{"ranked_sections": [{"section_id": "sec_a1", "confidence": 5.0}]}'
            )

    @pytest.mark.anyio
    async def test_too_many_ranked_items_raises(self) -> None:
        """A pathologically large ranking is rejected."""
        items = ", ".join(
            f'{{"section_id": "sec_{i}", "confidence": 0.5}}'
            for i in range(MAX_RANKED_ITEMS + 1)
        )
        with pytest.raises(ValueError, match="schema validation"):
            parse_router_llm_json(f'{{"ranked_sections": [{items}]}}')


class TestExtractJsonObject:
    """The brace-balanced object extractor."""

    @pytest.mark.anyio
    async def test_no_object_raises(self) -> None:
        """Text with no opening brace raises."""
        with pytest.raises(ValueError, match="no JSON object"):
            _extract_json_object("no json here")

    @pytest.mark.anyio
    async def test_unbalanced_object_raises(self) -> None:
        """An unterminated object raises."""
        with pytest.raises(ValueError, match="unbalanced"):
            _extract_json_object('{"a": 1')

    @pytest.mark.anyio
    async def test_braces_inside_strings_are_ignored(self) -> None:
        """Braces inside string literals do not affect nesting depth."""
        extracted = _extract_json_object('prefix {"a": "}{"} suffix')
        assert extracted == '{"a": "}{"}'

    @pytest.mark.anyio
    async def test_escaped_characters_in_strings_are_handled(self) -> None:
        """Escaped quotes/backslashes inside a string literal are skipped."""
        extracted = _extract_json_object(r'{"a": "esc\" and \\ end"}')
        assert extracted == r'{"a": "esc\" and \\ end"}'


class TestRankedSection:
    """The section-id shape validator (cheap first-pass injection guard)."""

    @pytest.mark.anyio
    async def test_bad_section_id_pattern_rejected(self) -> None:
        """A section id not matching the universal pattern is rejected."""
        with pytest.raises(ValueError, match="pattern"):
            RankedSection(section_id="DROP TABLE", confidence=0.5)


class TestApplyThreshold:
    """The confidence-thresholding floor invariant (FINDING #8 regression)."""

    @pytest.mark.anyio
    async def test_low_threshold_does_not_admit_sub_floor_section(self) -> None:
        """A threshold below the floor must not select a sub-0.5 section.

        With ``confidence_threshold=0.4`` and the only candidate at 0.45, the
        section is below ``LOW_CONFIDENCE_FLOOR`` and must be excluded, leaving
        an empty selection that signals fallback upstream.
        """
        from router.graph import _apply_threshold
        from router.schema import RankedSection

        ranked = [RankedSection(section_id="sec_a1", confidence=0.45)]
        selected = _apply_threshold(ranked, confidence_threshold=0.4, max_sections=3)
        assert selected == []

    @pytest.mark.anyio
    async def test_low_threshold_keeps_eligible_section(self) -> None:
        """A section at or above the floor is still selected under a low threshold."""
        from router.graph import _apply_threshold
        from router.schema import RankedSection

        ranked = [
            RankedSection(section_id="sec_a1", confidence=0.45),
            RankedSection(section_id="sec_b2", confidence=0.6),
        ]
        selected = _apply_threshold(ranked, confidence_threshold=0.4, max_sections=3)
        assert [item.section_id for item in selected] == ["sec_b2"]

    @pytest.mark.anyio
    async def test_normal_threshold_high_band_unchanged(self) -> None:
        """The normal case (threshold >= floor) preserves high-band behavior."""
        from router.graph import _apply_threshold
        from router.schema import RankedSection

        ranked = [
            RankedSection(section_id="sec_a1", confidence=0.9),
            RankedSection(section_id="sec_b2", confidence=0.6),
        ]
        selected = _apply_threshold(ranked, confidence_threshold=0.7, max_sections=3)
        assert [item.section_id for item in selected] == ["sec_a1"]

    @pytest.mark.anyio
    async def test_normal_threshold_mid_band_unchanged(self) -> None:
        """The mid band fires when no section reaches the threshold."""
        from router.graph import _apply_threshold
        from router.schema import RankedSection

        ranked = [
            RankedSection(section_id="sec_a1", confidence=0.6),
            RankedSection(section_id="sec_b2", confidence=0.55),
        ]
        selected = _apply_threshold(ranked, confidence_threshold=0.7, max_sections=3)
        assert [item.section_id for item in selected] == ["sec_a1", "sec_b2"]


class TestTocCacheAndGraph:
    """The TOC projection cache and the offline pipeline path."""

    @pytest.mark.anyio
    async def test_toc_cache_evicts_when_full(self) -> None:
        """The TOC JSON cache evicts the oldest entry past its max size."""
        from router import graph as graph_mod

        graph_mod.clear_toc_cache()
        toc = [{"section_id": "sec_a1", "title": "T", "page_start": 1, "page_end": 2}]
        for index in range(graph_mod._TOC_CACHE_MAXSIZE + 5):
            graph_mod._cached_toc_json(f"doc_{index}", toc)
        assert len(graph_mod._TOC_JSON_CACHE) <= graph_mod._TOC_CACHE_MAXSIZE
        graph_mod.clear_toc_cache()

    @pytest.mark.anyio
    async def test_toc_cache_hit_returns_same_string(self) -> None:
        """A repeated doc_id returns the cached projection (cache hit branch)."""
        from router import graph as graph_mod

        graph_mod.clear_toc_cache()
        toc = [{"section_id": "sec_a1", "title": "T", "page_start": 1, "page_end": 2}]
        first = graph_mod._cached_toc_json("doc_hit", toc)
        second = graph_mod._cached_toc_json("doc_hit", toc)
        assert first == second
        graph_mod.clear_toc_cache()

    @pytest.mark.anyio
    async def test_build_langgraph_returns_none_when_import_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When langgraph cannot be imported, the graph falls back to the pipeline."""
        import builtins

        from router.graph import RouterGraph, _build_langgraph
        from router.llm import FakeRouterLLM

        real_import = builtins.__import__

        def _blocked_import(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("langgraph"):
                raise ImportError("langgraph blocked for test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _blocked_import)
        llm = FakeRouterLLM('{"ranked_sections": [], "rationale": "x"}')
        assert _build_langgraph(llm) is None
        graph = RouterGraph(llm)
        assert graph.backend == "async-pipeline"
        toc = [{"section_id": "sec_a1", "title": "T", "page_start": 1, "page_end": 9}]
        output = await graph.run(
            query="q",
            doc_id="doc_1",
            toc=toc,
            tenant_id="tenant_a",
            confidence_threshold=0.7,
            max_sections=3,
        )
        assert output.fallback is True

    @pytest.mark.anyio
    async def test_pipeline_fallback_runs_without_langgraph(self) -> None:
        """The async pipeline fallback produces a valid RouterOutput offline."""
        from router.graph import RouterGraph, _run_pipeline_fallback
        from router.llm import FakeRouterLLM

        llm = FakeRouterLLM(
            '{"ranked_sections": [{"section_id": "sec_a1", "confidence": 0.9}],'
            ' "rationale": "matched"}'
        )
        toc = [{"section_id": "sec_a1", "title": "T", "page_start": 1, "page_end": 9}]
        state = {
            "query": "q",
            "doc_id": "doc_1",
            "toc": toc,
            "tenant_id": "tenant_a",
            "confidence_threshold": 0.7,
            "max_sections": 3,
        }
        final = await _run_pipeline_fallback(state, llm)
        assert final["output"].relevant_sections == ["sec_a1"]

        graph = RouterGraph(llm)
        assert graph.backend in {"langgraph", "async-pipeline"}


class TestRoutePackageEntrypoint:
    """The ``router.route`` package entrypoint."""

    @pytest.mark.anyio
    async def test_route_with_injected_fake_llm(self) -> None:
        """route() runs end-to-end with an injected fake LLM and returns a dict."""
        from router import route
        from router.llm import FakeRouterLLM

        llm = FakeRouterLLM(
            '{"ranked_sections": [{"section_id": "sec_a1", "confidence": 0.9}],'
            ' "rationale": "matched"}'
        )
        toc = [{"section_id": "sec_a1", "title": "T", "page_start": 1, "page_end": 9}]
        result = await route("q", "doc_1", toc, tenant_id="tenant_a", llm=llm)
        assert result["relevant_sections"] == ["sec_a1"]
        assert result["fallback"] is False

    @pytest.mark.anyio
    async def test_route_constructs_default_llm_when_omitted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """route() builds a default ClaudeHaikuRouterLLM when no llm is passed.

        The default LLM is stubbed so no Anthropic client or key is needed; this
        exercises the default-construction branch in ``router.route``.
        """
        import router.llm as llm_mod
        from router import route

        class _StubLLM:
            async def complete(self, system: str, messages: list) -> str:
                return '{"ranked_sections": [], "rationale": "fallback"}'

        monkeypatch.setattr(llm_mod, "ClaudeHaikuRouterLLM", lambda: _StubLLM())
        toc = [{"section_id": "sec_a1", "title": "T", "page_start": 1, "page_end": 9}]
        result = await route("q", "doc_1", toc, tenant_id="tenant_a")
        assert result["fallback"] is True
