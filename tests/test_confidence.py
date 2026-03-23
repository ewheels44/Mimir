"""Tests for mimir.extraction.confidence — ConfidenceScorer."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from mimir.extraction.confidence import ConfidenceScorer, ConfidenceThreshold, ScoredFact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_openai_response(score: float, reasoning: str) -> MagicMock:
    """Build a minimal mock that looks like an openai ChatCompletion response."""
    payload = json.dumps({"score": score, "reasoning": reasoning})
    message = MagicMock()
    message.content = payload
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_scorer(score: float, reasoning: str = "test reasoning") -> ConfidenceScorer:
    """Return a ConfidenceScorer whose LLM call is mocked to return *score*."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_openai_response(score, reasoning)
    return ConfidenceScorer(client=mock_client)


# ---------------------------------------------------------------------------
# score_extraction — return type and structure
# ---------------------------------------------------------------------------


class TestScoreExtractionReturnType:
    def test_returns_scored_fact_instance(self):
        scorer = _make_scorer(0.90)
        result = scorer.score_extraction(
            "User prefers dark mode.", "User said: I prefer dark mode."
        )
        assert isinstance(result, ScoredFact)

    def test_scored_fact_preserves_fact_and_context(self):
        fact = "User prefers dark mode."
        context = "User said: I prefer dark mode."
        scorer = _make_scorer(0.90)
        result = scorer.score_extraction(fact, context)
        assert result.fact == fact
        assert result.context == context

    def test_score_is_float(self):
        scorer = _make_scorer(0.75)
        result = scorer.score_extraction("fact", "context")
        assert isinstance(result.score, float)

    def test_score_in_range(self):
        scorer = _make_scorer(0.75)
        result = scorer.score_extraction("fact", "context")
        assert 0.0 <= result.score <= 1.0

    def test_reasoning_is_string(self):
        scorer = _make_scorer(0.80, reasoning="Clearly stated in context.")
        result = scorer.score_extraction("fact", "context")
        assert isinstance(result.reasoning, str)
        assert result.reasoning == "Clearly stated in context."


# ---------------------------------------------------------------------------
# Threshold classification
# ---------------------------------------------------------------------------


class TestThresholdClassification:
    """Verify the three threshold bands are applied correctly."""

    # --- REJECT band: score < 0.70 ---

    @pytest.mark.parametrize("score", [0.0, 0.10, 0.50, 0.69, 0.699])
    def test_reject_below_threshold(self, score: float):
        scorer = _make_scorer(score)
        result = scorer.score_extraction("fact", "context")
        assert result.threshold == ConfidenceThreshold.REJECT

    def test_reject_at_zero(self):
        scorer = _make_scorer(0.0)
        result = scorer.score_extraction("fact", "context")
        assert result.threshold == ConfidenceThreshold.REJECT

    # --- REVIEW band: 0.70 ≤ score ≤ 0.85 ---

    @pytest.mark.parametrize("score", [0.70, 0.75, 0.80, 0.85])
    def test_review_in_band(self, score: float):
        scorer = _make_scorer(score)
        result = scorer.score_extraction("fact", "context")
        assert result.threshold == ConfidenceThreshold.REVIEW

    def test_review_at_lower_boundary(self):
        scorer = _make_scorer(0.70)
        result = scorer.score_extraction("fact", "context")
        assert result.threshold == ConfidenceThreshold.REVIEW

    def test_review_at_upper_boundary(self):
        scorer = _make_scorer(0.85)
        result = scorer.score_extraction("fact", "context")
        assert result.threshold == ConfidenceThreshold.REVIEW

    # --- AUTO_STAGE band: score > 0.85 ---

    @pytest.mark.parametrize("score", [0.851, 0.90, 0.95, 1.0])
    def test_auto_stage_above_threshold(self, score: float):
        scorer = _make_scorer(score)
        result = scorer.score_extraction("fact", "context")
        assert result.threshold == ConfidenceThreshold.AUTO_STAGE

    def test_auto_stage_at_one(self):
        scorer = _make_scorer(1.0)
        result = scorer.score_extraction("fact", "context")
        assert result.threshold == ConfidenceThreshold.AUTO_STAGE


# ---------------------------------------------------------------------------
# Score clamping
# ---------------------------------------------------------------------------


class TestScoreClamping:
    """LLM may return out-of-range values; they must be clamped to [0, 1]."""

    def test_clamp_above_one(self):
        scorer = _make_scorer(1.5)
        result = scorer.score_extraction("fact", "context")
        assert result.score == 1.0
        assert result.threshold == ConfidenceThreshold.AUTO_STAGE

    def test_clamp_below_zero(self):
        scorer = _make_scorer(-0.3)
        result = scorer.score_extraction("fact", "context")
        assert result.score == 0.0
        assert result.threshold == ConfidenceThreshold.REJECT


# ---------------------------------------------------------------------------
# LLM call mechanics
# ---------------------------------------------------------------------------


class TestLLMCallMechanics:
    def test_llm_called_once_per_score_extraction(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(0.90, "ok")
        scorer = ConfidenceScorer(client=mock_client)
        scorer.score_extraction("fact", "context")
        mock_client.chat.completions.create.assert_called_once()

    def test_fact_and_context_appear_in_llm_call(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(0.90, "ok")
        scorer = ConfidenceScorer(client=mock_client)
        fact = "User prefers tabs over spaces."
        context = "User explicitly stated: use tabs, not spaces."
        scorer.score_extraction(fact, context)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
        # Find the user message
        user_msg = next(m for m in messages if m["role"] == "user")
        assert fact in user_msg["content"]
        assert context in user_msg["content"]

    def test_default_model_is_gpt4o_mini(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(0.90, "ok")
        scorer = ConfidenceScorer(client=mock_client)
        scorer.score_extraction("fact", "context")
        call_kwargs = mock_client.chat.completions.create.call_args
        model = call_kwargs.kwargs.get("model") or call_kwargs.args[0]
        assert model == "gpt-4o-mini"

    def test_custom_model_is_forwarded(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(0.90, "ok")
        scorer = ConfidenceScorer(client=mock_client, model="gpt-4o")
        scorer.score_extraction("fact", "context")
        call_kwargs = mock_client.chat.completions.create.call_args
        model = call_kwargs.kwargs.get("model") or call_kwargs.args[0]
        assert model == "gpt-4o"

    def test_temperature_zero_by_default(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(0.90, "ok")
        scorer = ConfidenceScorer(client=mock_client)
        scorer.score_extraction("fact", "context")
        call_kwargs = mock_client.chat.completions.create.call_args
        temperature = call_kwargs.kwargs.get("temperature")
        assert temperature == 0.0


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


class TestResponseParsing:
    def test_parses_plain_json(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(0.88, "clear")
        scorer = ConfidenceScorer(client=mock_client)
        result = scorer.score_extraction("fact", "context")
        assert result.score == pytest.approx(0.88)
        assert result.reasoning == "clear"

    def test_parses_json_with_markdown_fences(self):
        """LLMs sometimes wrap JSON in ```json ... ``` fences."""
        payload = '```json\n{"score": 0.77, "reasoning": "fenced"}\n```'
        message = MagicMock()
        message.content = payload
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = response
        scorer = ConfidenceScorer(client=mock_client)
        result = scorer.score_extraction("fact", "context")
        assert result.score == pytest.approx(0.77)
        assert result.reasoning == "fenced"

    def test_raises_on_non_json_response(self):
        message = MagicMock()
        message.content = "I cannot evaluate this."
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = response
        scorer = ConfidenceScorer(client=mock_client)
        with pytest.raises(ValueError, match="non-JSON"):
            scorer.score_extraction("fact", "context")

    def test_raises_on_missing_score_key(self):
        payload = json.dumps({"reasoning": "no score here"})
        message = MagicMock()
        message.content = payload
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = response
        scorer = ConfidenceScorer(client=mock_client)
        with pytest.raises(ValueError, match="missing 'score'"):
            scorer.score_extraction("fact", "context")

    def test_raises_on_missing_reasoning_key(self):
        payload = json.dumps({"score": 0.80})
        message = MagicMock()
        message.content = payload
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = response
        scorer = ConfidenceScorer(client=mock_client)
        with pytest.raises(ValueError, match="missing 'reasoning'"):
            scorer.score_extraction("fact", "context")

    def test_raises_on_non_numeric_score(self):
        payload = json.dumps({"score": "high", "reasoning": "bad type"})
        message = MagicMock()
        message.content = payload
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = response
        scorer = ConfidenceScorer(client=mock_client)
        with pytest.raises(ValueError, match="not a valid float"):
            scorer.score_extraction("fact", "context")


# ---------------------------------------------------------------------------
# classify() standalone helper
# ---------------------------------------------------------------------------


class TestClassifyHelper:
    def test_classify_reject(self):
        scorer = ConfidenceScorer(client=MagicMock())
        assert scorer.classify(0.0) == ConfidenceThreshold.REJECT
        assert scorer.classify(0.69) == ConfidenceThreshold.REJECT

    def test_classify_review(self):
        scorer = ConfidenceScorer(client=MagicMock())
        assert scorer.classify(0.70) == ConfidenceThreshold.REVIEW
        assert scorer.classify(0.85) == ConfidenceThreshold.REVIEW

    def test_classify_auto_stage(self):
        scorer = ConfidenceScorer(client=MagicMock())
        assert scorer.classify(0.86) == ConfidenceThreshold.AUTO_STAGE
        assert scorer.classify(1.0) == ConfidenceThreshold.AUTO_STAGE


# ---------------------------------------------------------------------------
# Default client construction (no API key needed — just checks no crash)
# ---------------------------------------------------------------------------


class TestDefaultClientConstruction:
    def test_default_client_created_when_none_passed(self):
        """ConfidenceScorer should not crash on construction without a client."""
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_openai_cls.return_value = MagicMock()
            scorer = ConfidenceScorer()
            mock_openai_cls.assert_called_once()
            assert scorer is not None
