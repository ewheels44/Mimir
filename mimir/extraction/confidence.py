"""Confidence Scoring module for extracted facts.

Uses an LLM to evaluate how confident we are that an extracted fact is accurate,
well-supported by context, and worth storing as a memory.

Thresholds:
    - score < 0.70  → reject (discard the fact)
    - 0.70 ≤ score ≤ 0.85 → review queue (human review required)
    - score > 0.85  → auto-stage (automatically staged for storage)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

import openai


class ConfidenceThreshold(str, Enum):
    """Disposition of a scored fact based on its confidence score."""

    REJECT = "reject"
    REVIEW = "review"
    AUTO_STAGE = "auto_stage"


@dataclass
class ScoredFact:
    """A fact paired with its LLM-assigned confidence score and disposition."""

    fact: str
    context: str
    score: float
    threshold: ConfidenceThreshold
    reasoning: str


_SYSTEM_PROMPT = """\
You are a fact-confidence evaluator for a memory system.

Given an extracted fact and the context it was drawn from, evaluate how confident
you are that:
1. The fact is accurately stated (not hallucinated or distorted).
2. The fact is well-supported by the provided context.
3. The fact is specific and actionable (not vague or trivially obvious).

Respond with a JSON object containing exactly two keys:
- "score": a float between 0.0 and 1.0 (higher = more confident)
- "reasoning": a brief one-sentence explanation of your score

Example response:
{"score": 0.92, "reasoning": "The fact is directly stated in the context with no ambiguity."}

Do not include any text outside the JSON object.
"""

_USER_TEMPLATE = """\
Extracted fact:
{fact}

Context:
{context}
"""


class ConfidenceScorer:
    """Scores extracted facts using an LLM to determine storage disposition.

    Uses the OpenAI chat completions API to evaluate each fact against its
    source context. Returns a :class:`ScoredFact` with a 0.0–1.0 confidence
    score and a :class:`ConfidenceThreshold` disposition.

    Args:
        client: An ``openai.OpenAI`` client instance. If ``None``, a default
            client is created (reads ``OPENAI_API_KEY`` from the environment).
        model: The OpenAI model to use for scoring. Defaults to
            ``"gpt-4o-mini"`` for cost efficiency.
        temperature: Sampling temperature for the LLM. Defaults to ``0.0``
            for deterministic scoring.
    """

    REJECT_THRESHOLD: float = 0.70
    AUTO_STAGE_THRESHOLD: float = 0.85

    def __init__(
        self,
        client: openai.OpenAI | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ) -> None:
        self._client = client if client is not None else openai.OpenAI()
        self._model = model
        self._temperature = temperature

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_extraction(self, fact: str, context: str) -> ScoredFact:
        """Score an extracted fact against its source context.

        Calls the LLM to evaluate the fact and returns a :class:`ScoredFact`
        with a confidence score in [0.0, 1.0] and a disposition.

        Args:
            fact: The extracted fact to evaluate (a short, declarative string).
            context: The source text from which the fact was extracted.

        Returns:
            A :class:`ScoredFact` with ``score``, ``threshold``, and
            ``reasoning`` populated.

        Raises:
            ValueError: If the LLM response cannot be parsed as valid JSON
                with the expected schema.
            openai.OpenAIError: If the API call fails.
        """
        raw_score, reasoning = self._call_llm(fact, context)
        score = self._clamp(raw_score)
        threshold = self._classify(score)

        return ScoredFact(
            fact=fact,
            context=context,
            score=score,
            threshold=threshold,
            reasoning=reasoning,
        )

    def classify(self, score: float) -> ConfidenceThreshold:
        """Return the :class:`ConfidenceThreshold` for a given score.

        Useful for re-classifying a score without calling the LLM again.

        Args:
            score: A float in [0.0, 1.0].

        Returns:
            The corresponding :class:`ConfidenceThreshold`.
        """
        return self._classify(score)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_llm(self, fact: str, context: str) -> tuple[float, str]:
        """Call the LLM and return (score, reasoning).

        Args:
            fact: The extracted fact.
            context: The source context.

        Returns:
            A tuple of (score: float, reasoning: str).

        Raises:
            ValueError: If the response JSON is malformed or missing keys.
        """
        user_message = _USER_TEMPLATE.format(fact=fact, context=context)

        response = self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )

        raw_content = response.choices[0].message.content or ""
        return self._parse_response(raw_content)

    def _parse_response(self, content: str) -> tuple[float, str]:
        """Parse the LLM JSON response into (score, reasoning).

        Strips markdown code fences if present before parsing.

        Args:
            content: Raw string content from the LLM.

        Returns:
            A tuple of (score: float, reasoning: str).

        Raises:
            ValueError: If JSON is invalid or required keys are missing.
        """
        # Strip optional markdown code fences (```json ... ```)
        cleaned = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())

        try:
            data: dict[str, Any] = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned non-JSON response: {content!r}") from exc

        if "score" not in data:
            raise ValueError(f"LLM response missing 'score' key: {data!r}")
        if "reasoning" not in data:
            raise ValueError(f"LLM response missing 'reasoning' key: {data!r}")

        try:
            score = float(data["score"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"LLM 'score' is not a valid float: {data['score']!r}") from exc

        reasoning = str(data["reasoning"])
        return score, reasoning

    @staticmethod
    def _clamp(score: float) -> float:
        """Clamp score to [0.0, 1.0]."""
        return max(0.0, min(1.0, score))

    def _classify(self, score: float) -> ConfidenceThreshold:
        """Map a score to a :class:`ConfidenceThreshold`.

        Args:
            score: A float in [0.0, 1.0].

        Returns:
            - ``REJECT`` if score < 0.70
            - ``REVIEW`` if 0.70 ≤ score ≤ 0.85
            - ``AUTO_STAGE`` if score > 0.85
        """
        if score < self.REJECT_THRESHOLD:
            return ConfidenceThreshold.REJECT
        if score <= self.AUTO_STAGE_THRESHOLD:
            return ConfidenceThreshold.REVIEW
        return ConfidenceThreshold.AUTO_STAGE
