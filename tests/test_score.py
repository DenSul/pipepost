"""Tests for ScoringStep — LLM-based candidate ranking."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipepost.core.context import Candidate, FlowContext
from pipepost.steps.score import ScoringStep


def _make_candidates(n):
    return [
        Candidate(
            url=f"https://example.com/{i}",
            title=f"Article {i}",
            source_name="test",
        )
        for i in range(n)
    ]


def _make_llm_response(text):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = text
    return mock_response


def _scores_json(scores):
    """Build a JSON string from a list of (1-based index, score, reason) tuples."""
    return json.dumps([{"index": idx, "score": s, "reason": r} for idx, s, r in scores])


class TestScoringStepExecute:
    @pytest.mark.asyncio
    async def test_reorders_candidates_by_score(self):
        step = ScoringStep(model="test-model", niche="tech")
        ctx = FlowContext()
        ctx.candidates = _make_candidates(3)

        scores = _scores_json(
            [
                (1, 50, "OK"),
                (2, 90, "Great"),
                (3, 70, "Good"),
            ]
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _make_llm_response(scores)
            ctx = await step.execute(ctx)

        assert ctx.candidates[0].title == "Article 1"  # index 2 (0-based=1), score 90
        assert ctx.candidates[1].title == "Article 2"  # index 3 (0-based=2), score 70
        assert ctx.candidates[2].title == "Article 0"  # index 1 (0-based=0), score 50

    @pytest.mark.asyncio
    async def test_llm_failure_keeps_original_order(self):
        step = ScoringStep(model="test-model")
        ctx = FlowContext()
        ctx.candidates = _make_candidates(3)
        original_titles = [c.title for c in ctx.candidates]

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("API down")
            ctx = await step.execute(ctx)

        assert [c.title for c in ctx.candidates] == original_titles
        assert not ctx.has_errors  # no error added, graceful degradation

    @pytest.mark.asyncio
    async def test_max_score_candidates_limits_input(self):
        step = ScoringStep(model="test-model", max_score_candidates=2)
        ctx = FlowContext()
        ctx.candidates = _make_candidates(5)

        scores = _scores_json(
            [
                (1, 60, "OK"),
                (2, 80, "Good"),
            ]
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _make_llm_response(scores)
            ctx = await step.execute(ctx)

        # Only first 2 scored, then 3 remaining appended
        assert len(ctx.candidates) == 5
        # Top candidate should be Article 1 (0-based idx=1, score 80)
        assert ctx.candidates[0].title == "Article 1"

    @pytest.mark.asyncio
    async def test_updates_candidate_scores(self):
        step = ScoringStep(model="test-model")
        ctx = FlowContext()
        ctx.candidates = _make_candidates(2)

        scores = _scores_json(
            [
                (1, 75, "Good"),
                (2, 95, "Excellent"),
            ]
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _make_llm_response(scores)
            ctx = await step.execute(ctx)

        # After reordering, first candidate has score 95
        assert ctx.candidates[0].score == 95.0
        assert ctx.candidates[1].score == 75.0


class TestScoringStepShouldSkip:
    def test_skips_no_candidates(self):
        step = ScoringStep()
        ctx = FlowContext()
        assert step.should_skip(ctx) is True

    def test_skips_single_candidate(self):
        step = ScoringStep()
        ctx = FlowContext()
        ctx.candidates = _make_candidates(1)
        assert step.should_skip(ctx) is True

    def test_does_not_skip_multiple_candidates(self):
        step = ScoringStep()
        ctx = FlowContext()
        ctx.candidates = _make_candidates(3)
        assert step.should_skip(ctx) is False


class TestBuildScoringPrompt:
    def test_prompt_contains_niche(self):
        step = ScoringStep(niche="finance")
        candidates = _make_candidates(2)
        prompt = step._build_scoring_prompt(candidates)
        assert "finance" in prompt

    def test_prompt_contains_candidate_titles(self):
        step = ScoringStep(niche="tech")
        candidates = _make_candidates(2)
        prompt = step._build_scoring_prompt(candidates)
        assert "Article 0" in prompt
        assert "Article 1" in prompt

    def test_prompt_contains_candidate_urls(self):
        step = ScoringStep(niche="general")
        candidates = _make_candidates(2)
        prompt = step._build_scoring_prompt(candidates)
        assert "https://example.com/0" in prompt
        assert "https://example.com/1" in prompt


class TestParseScores:
    def test_parse_scores_valid_json(self):
        step = ScoringStep()
        raw = json.dumps(
            [
                {"index": 1, "score": 85, "reason": "Great"},
                {"index": 2, "score": 60, "reason": "OK"},
            ]
        )
        result = step._parse_scores(raw, 2)
        assert result == [(0, 85.0), (1, 60.0)]

    def test_parse_scores_with_markdown_code_block(self):
        step = ScoringStep()
        raw = '```json\n[{"index": 1, "score": 90, "reason": "Top"}]\n```'
        result = step._parse_scores(raw, 1)
        assert result == [(0, 90.0)]

    def test_parse_scores_invalid_json_returns_empty(self):
        step = ScoringStep()
        result = step._parse_scores("not valid json at all", 3)
        assert result == []

    def test_parse_scores_out_of_range_index_ignored(self):
        step = ScoringStep()
        raw = json.dumps(
            [
                {"index": 1, "score": 80, "reason": "OK"},
                {"index": 99, "score": 50, "reason": "Out of range"},
            ]
        )
        result = step._parse_scores(raw, 2)
        assert len(result) == 1
        assert result[0] == (0, 80.0)

    def test_parse_scores_missing_fields_skipped(self):
        step = ScoringStep()
        raw = json.dumps(
            [
                {"index": 1, "score": 80, "reason": "OK"},
                {"index": 2},  # missing score
                {"score": 70},  # missing index
            ]
        )
        result = step._parse_scores(raw, 3)
        assert len(result) == 1
