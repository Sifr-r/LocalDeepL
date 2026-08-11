"""
Focused unit tests for the LLM-based ``evaluate_node`` and its helpers.

Covers:
- The four fast paths (translation error, max-attempts, punctuation, length ratio)
  are preserved end-to-end through the async refactor.
- The real LLM path parses direct / fenced / embedded JSON robustly.
- The real LLM path falls back to ``(1.0, "")`` on call_llm errors or
  unrecoverable responses — so a transient LLM outage can't trap the graph.
- Prompt construction includes target language and (when present) RAG context.
- Score values are clamped to [0, 1]; non-numeric scores fall back.

The heuristic-only fast paths are also exercised by ``test_security_qa.py``
and ``test_translation_boundary.py``; this file is the LLM-path drill-down.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from omniscribe.core import translation
from omniscribe.core.translation import (
    TranslationState,
    build_evaluation_prompt,
    evaluate_node,
    parse_evaluation_response,
)
from omniscribe.core.translation_config import (
    DEFAULT_TRANSLATION_ACCEPTANCE_SCORE,
    DEFAULT_TRANSLATION_MAX_ATTEMPTS,
    DEFAULT_TRANSLATION_MIN_LENGTH_RATIO,
    TranslationSettings,
)


def _settings() -> TranslationSettings:
    return TranslationSettings(
        api_base="https://example.test/v1",
        api_key="test-key",
        model="openai/test-model",
        max_attempts=DEFAULT_TRANSLATION_MAX_ATTEMPTS,
        min_length_ratio=DEFAULT_TRANSLATION_MIN_LENGTH_RATIO,
        acceptance_score=DEFAULT_TRANSLATION_ACCEPTANCE_SCORE,
    )


def _state(
    *,
    source: str = "Hello world, this is a normal English sentence.",
    translation_: str = "Bonjour le monde, ceci est une phrase normale.",
    target_language: str = "French",
    rag_context: list[str] | None = None,
    attempts: int = 1,
) -> TranslationState:
    # Default to a non-empty glossary so LLM-path tests reach the LLM call.
    # Tests that exercise the §2.5 "no glossary" fast path pass an explicit
    # ``rag_context=[]`` to bypass the accept-within-band gate.
    if rag_context is None:
        rag_context = ["placeholder glossary term"]
    return {
        "source_chunk": source,
        "target_language": target_language,
        "rag_context": rag_context,
        "translated_chunk": translation_,
        "evaluation_score": 1.0,
        "feedback": "",
        "attempts": attempts,
        "settings": _settings(),
    }


# ---------------------------------------------------------------------------
# Fast paths (no LLM call)
# ---------------------------------------------------------------------------


class TestEvaluateFastPaths:
    async def test_translation_error_prefix_skips_llm(self) -> None:
        state = _state(translation_="[Translation Error: Connection refused]")
        with patch.object(
            translation, "_llm_evaluate_translation", new=AsyncMock()
        ) as llm:
            result = await evaluate_node(state)
        llm.assert_not_called()
        assert result == {
            "evaluation_score": 0.0,
            "feedback": "Translation API call failed.",
        }

    async def test_translation_error_after_max_attempts_forces_accept(self) -> None:
        state = _state(
            translation_="[Translation Error: timeout]",
            attempts=DEFAULT_TRANSLATION_MAX_ATTEMPTS,
        )
        with patch.object(
            translation, "_llm_evaluate_translation", new=AsyncMock()
        ) as llm:
            result = await evaluate_node(state)
        llm.assert_not_called()
        assert result["evaluation_score"] == 1.0

    async def test_max_attempts_without_error_forces_accept(self) -> None:
        # Even with a real-looking translation, attempts >= settings.max_attempts
        # must short-circuit to 1.0 to prevent infinite loops.
        state = _state(
            translation_="Bonjour", attempts=DEFAULT_TRANSLATION_MAX_ATTEMPTS
        )
        with patch.object(
            translation, "_llm_evaluate_translation", new=AsyncMock()
        ) as llm:
            result = await evaluate_node(state)
        llm.assert_not_called()
        assert result == {"evaluation_score": 1.0, "feedback": ""}

    async def test_short_source_skips_llm(self) -> None:
        state = _state(source="hi", translation_="salut")
        with patch.object(
            translation, "_llm_evaluate_translation", new=AsyncMock()
        ) as llm:
            result = await evaluate_node(state)
        llm.assert_not_called()
        assert result == {"evaluation_score": 1.0, "feedback": "Looks good"}

    async def test_punctuation_only_source_skips_llm(self) -> None:
        state = _state(source="!!!", translation_="???")
        with patch.object(
            translation, "_llm_evaluate_translation", new=AsyncMock()
        ) as llm:
            result = await evaluate_node(state)
        llm.assert_not_called()
        assert result["evaluation_score"] == 1.0

    async def test_length_ratio_below_threshold_skips_llm(self) -> None:
        long_source = (
            "This is a substantial source text that the translator must convert "
            "in full, with at least some faithful correspondence."
        )
        # Translation is 5% of source length — well below settings.min_length_ratio.
        state = _state(source=long_source, translation_="short")
        with patch.object(
            translation, "_llm_evaluate_translation", new=AsyncMock()
        ) as llm:
            result = await evaluate_node(state)
        llm.assert_not_called()
        assert result["evaluation_score"] == 0.0
        assert "too short" in result["feedback"]

    async def test_length_ratio_above_max_skips_llm(self) -> None:
        """§2.5 regression: translation > max_length_ratio × source is garbled."""
        source = "Short source."
        # Translation is 10× source length — well above the 2.5× default.
        state = _state(
            source=source,
            translation_="A" * (len(source) * 10),
        )
        with patch.object(
            translation, "_llm_evaluate_translation", new=AsyncMock()
        ) as llm:
            result = await evaluate_node(state)
        llm.assert_not_called()
        assert result["evaluation_score"] == 0.0
        assert "too long" in result["feedback"]

    async def test_length_ratio_in_band_no_glossary_skips_llm(self) -> None:
        """§2.5 regression: in-band length + no glossary → accept without LLM."""
        source = "This is a normal-length source sentence to translate."
        translation_ = "C'est une phrase source de longueur normale à traduire."
        # rag_context=[] triggers the §2.5 accept-within-band fast path.
        state = _state(source=source, translation_=translation_, rag_context=[])
        with patch.object(
            translation, "_llm_evaluate_translation", new=AsyncMock()
        ) as llm:
            result = await evaluate_node(state)
        llm.assert_not_called()
        assert result["evaluation_score"] == 1.0
        assert "no glossary" in result["feedback"]

    async def test_length_ratio_in_band_with_glossary_calls_llm(self) -> None:
        """§2.5 regression: in-band length + non-empty glossary → still hits LLM."""
        source = "This is a normal-length source sentence to translate."
        translation_ = "C'est une phrase source de longueur normale à traduire."
        # Default rag_context is non-empty; LLM must be called.
        state = _state(source=source, translation_=translation_)
        with patch.object(
            translation,
            "_llm_evaluate_translation",
            new=AsyncMock(return_value=(0.9, "looks good")),
        ) as llm:
            result = await evaluate_node(state)
        llm.assert_called_once()
        assert result == {"evaluation_score": 0.9, "feedback": "looks good"}

    async def test_length_ratio_at_max_boundary_passes_upper_bound(self) -> None:
        """§2.5 regression: length ratio exactly at max_ratio is still in band.

        The check is strict ``>`` not ``>=``, so an exactly-at-max translation
        does NOT trigger the upper-bound fast path. With a non-empty glossary
        the translation continues to the LLM (proving the upper-bound check
        did not short-circuit).
        """
        source = "Short."  # 6 chars
        # 2.5 × 6 = 15. Build a translation of exactly 15 chars.
        translation_ = "X" * int(len(source) * 2.5)
        state = _state(source=source, translation_=translation_)  # non-empty rag
        with patch.object(
            translation,
            "_llm_evaluate_translation",
            new=AsyncMock(return_value=(0.95, "fine")),
        ) as llm:
            result = await evaluate_node(state)
        # Upper-bound check (strict >) did NOT fire → LLM is called.
        llm.assert_called_once()
        assert result == {"evaluation_score": 0.95, "feedback": "fine"}


# ---------------------------------------------------------------------------
# Real LLM path
# ---------------------------------------------------------------------------


class TestEvaluateLLMPath:
    async def test_valid_json_response_propagates_score_and_feedback(self) -> None:
        state = _state()
        with patch.object(
            translation,
            "_llm_evaluate_translation",
            new=AsyncMock(return_value=(0.85, "Solid translation overall.")),
        ):
            result = await evaluate_node(state)
        assert result == {
            "evaluation_score": 0.85,
            "feedback": "Solid translation overall.",
        }

    async def test_falls_back_when_call_llm_raises(self) -> None:
        state = _state()
        with patch.object(
            translation,
            "_llm_evaluate_translation",
            new=AsyncMock(side_effect=RuntimeError("provider timeout")),
        ):
            result = await evaluate_node(state)
        # Transient LLM outage must not trap us in a retry loop.
        assert result == {"evaluation_score": 1.0, "feedback": ""}

    async def test_falls_back_when_response_unparseable(self) -> None:
        state = _state()
        with patch.object(
            translation,
            "_llm_evaluate_translation",
            new=AsyncMock(return_value=parse_evaluation_response("not json at all")),
        ):
            result = await evaluate_node(state)
        # _extract_json_object returns None → (1.0, "") falls through.
        assert result == {"evaluation_score": 1.0, "feedback": ""}

    async def test_score_below_threshold_will_route_to_refine(self) -> None:
        # Direct unit-test of the path that triggers should_refine → "translate".
        # We don't run the graph here; we just verify the score < 0.8 reaches
        # the state, which the router uses.
        state = _state()
        with patch.object(
            translation,
            "_llm_evaluate_translation",
            new=AsyncMock(return_value=(0.3, "Major omissions")),
        ):
            result = await evaluate_node(state)
        assert result["evaluation_score"] < 0.8
        assert "Major omissions" in result["feedback"]


# ---------------------------------------------------------------------------
# parse_evaluation_response
# ---------------------------------------------------------------------------


class TestParseEvaluationResponse:
    def test_direct_json_object(self) -> None:
        assert parse_evaluation_response(
            '{"score": 0.92, "feedback": "good", "issues": []}'
        ) == (0.92, "good")

    def test_fenced_json_block(self) -> None:
        text = '```json\n{"score": 0.5, "feedback": "fair"}\n```'
        assert parse_evaluation_response(text) == (0.5, "fair")

    def test_unfenced_code_block(self) -> None:
        text = '```\n{"score": 0.5, "feedback": "fair"}\n```'
        assert parse_evaluation_response(text) == (0.5, "fair")

    def test_embedded_json_in_prose(self) -> None:
        text = 'Here is my assessment: {"score": 0.4, "feedback": "issues"} — done.'
        assert parse_evaluation_response(text) == (0.4, "issues")

    def test_score_clamped_above_one(self) -> None:
        score, _ = parse_evaluation_response('{"score": 1.5, "feedback": "x"}')
        assert score == 1.0

    def test_score_clamped_below_zero(self) -> None:
        score, _ = parse_evaluation_response('{"score": -0.2, "feedback": "x"}')
        assert score == 0.0

    def test_missing_score_falls_back_to_one(self) -> None:
        # Without a score we can't tell quality; default-accept.
        assert parse_evaluation_response('{"feedback": "no score given"}') == (
            1.0,
            "no score given",
        )

    def test_missing_feedback_returns_empty_string(self) -> None:
        assert parse_evaluation_response('{"score": 0.5}') == (0.5, "")

    def test_boolean_score_is_rejected(self) -> None:
        # bool is a subclass of int in Python; without the explicit guard a JSON
        # `true` would coerce to 1.0 silently. Wrong-type scores fall back to
        # the default 1.0 while preserving the feedback string.
        assert parse_evaluation_response('{"score": true, "feedback": "yep"}') == (
            1.0,
            "yep",
        )

    def test_string_score_falls_back(self) -> None:
        assert parse_evaluation_response('{"score": "high", "feedback": "x"}') == (
            1.0,
            "x",
        )

    def test_unparseable_returns_fallback(self) -> None:
        assert parse_evaluation_response("not json at all") == (1.0, "")

    def test_empty_returns_fallback(self) -> None:
        assert parse_evaluation_response("") == (1.0, "")
        assert parse_evaluation_response("   \n  ") == (1.0, "")

    def test_non_dict_json_falls_back(self) -> None:
        # Top-level array or scalar is not a valid evaluation response.
        assert parse_evaluation_response("[0.5, 0.7]") == (1.0, "")
        assert parse_evaluation_response("42") == (1.0, "")


# ---------------------------------------------------------------------------
# build_evaluation_prompt
# ---------------------------------------------------------------------------


class TestBuildEvaluationPrompt:
    def test_includes_source_and_translation_and_target_language(self) -> None:
        prompt = build_evaluation_prompt(
            source="Hello",
            translation="Bonjour",
            target_language="French",
            rag_context=[],
        )
        assert "Hello" in prompt
        assert "Bonjour" in prompt
        assert "French" in prompt

    def test_includes_rag_context_when_present(self) -> None:
        prompt = build_evaluation_prompt(
            source="API gateway",
            translation="passerelle API",
            target_language="French",
            rag_context=["API gateway = passerelle API"],
        )
        assert "API gateway = passerelle API" in prompt
        assert "GLOSSARY" in prompt

    def test_omits_glossary_section_when_rag_empty(self) -> None:
        prompt = build_evaluation_prompt(
            source="Hello",
            translation="Bonjour",
            target_language="French",
            rag_context=[],
        )
        assert "GLOSSARY" not in prompt

    def test_specifies_json_output_format(self) -> None:
        prompt = build_evaluation_prompt(
            source="Hello",
            translation="Bonjour",
            target_language="French",
            rag_context=[],
        )
        assert "JSON" in prompt
        assert '"score"' in prompt
        assert '"feedback"' in prompt


# ---------------------------------------------------------------------------
# End-to-end helper chain (parse_evaluation_response exercises _extract_json_object)
# ---------------------------------------------------------------------------


class TestExtractJsonObject:
    def test_returns_first_dict_when_multiple_objects_in_text(self) -> None:
        text = '{"score": 0.7} prefix {"score": 0.3}'
        score, _ = parse_evaluation_response(text)
        assert score == 0.7

    def test_handles_whitespace_before_fenced_block(self) -> None:
        text = '  \n```json\n{"score": 0.4, "feedback": "ok"}\n```  '
        assert parse_evaluation_response(text) == (0.4, "ok")
