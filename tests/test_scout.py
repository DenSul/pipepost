"""Tests for ScoutStep — source candidate fetching and filtering."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from pipepost.core.context import Candidate, FlowContext
from pipepost.exceptions import SourceError
from pipepost.steps.scout import ScoutStep


@pytest.fixture
def scout_step():
    return ScoutStep(max_candidates=10)


def _make_candidates(count):
    return [
        Candidate(url=f"https://example.com/{i}", title=f"Article {i}", score=float(i))
        for i in range(count)
    ]


class TestScoutStepExecute:
    @pytest.mark.asyncio
    async def test_fetches_candidates_from_source(self, scout_step):
        candidates = _make_candidates(3)
        mock_source = AsyncMock()
        mock_source.fetch_candidates.return_value = candidates

        with patch("pipepost.steps.scout.get_source", return_value=mock_source):
            ctx = FlowContext(source_name="test_source")
            result = await scout_step.execute(ctx)

        assert result.candidates == candidates
        mock_source.fetch_candidates.assert_awaited_once_with(limit=10)

    @pytest.mark.asyncio
    async def test_filters_existing_urls(self, scout_step):
        candidates = _make_candidates(3)
        mock_source = AsyncMock()
        mock_source.fetch_candidates.return_value = candidates

        with patch("pipepost.steps.scout.get_source", return_value=mock_source):
            ctx = FlowContext(
                source_name="test_source",
                existing_urls={"https://example.com/0", "https://example.com/2"},
            )
            result = await scout_step.execute(ctx)

        assert len(result.candidates) == 1
        assert result.candidates[0].url == "https://example.com/1"

    @pytest.mark.asyncio
    async def test_no_source_name_skips(self, scout_step):
        ctx = FlowContext(source_name="")
        assert scout_step.should_skip(ctx) is True

    @pytest.mark.asyncio
    async def test_unknown_source_raises(self, scout_step):
        ctx = FlowContext(source_name="nonexistent")
        with (
            patch("pipepost.steps.scout.get_source", side_effect=KeyError("not found")),
            pytest.raises(SourceError, match="Unknown source"),
        ):
            await scout_step.execute(ctx)

    @pytest.mark.asyncio
    async def test_source_error_wrapped(self, scout_step):
        mock_source = AsyncMock()
        mock_source.fetch_candidates.side_effect = RuntimeError("connection failed")

        with patch("pipepost.steps.scout.get_source", return_value=mock_source):
            ctx = FlowContext(source_name="broken_source")
            with pytest.raises(SourceError, match="Failed to fetch candidates"):
                await scout_step.execute(ctx)

    @pytest.mark.asyncio
    async def test_source_error_not_double_wrapped(self, scout_step):
        mock_source = AsyncMock()
        mock_source.fetch_candidates.side_effect = SourceError("original error")

        with patch("pipepost.steps.scout.get_source", return_value=mock_source):
            ctx = FlowContext(source_name="broken_source")
            with pytest.raises(SourceError, match="original error"):
                await scout_step.execute(ctx)

    @pytest.mark.asyncio
    async def test_no_candidates_after_filter_adds_error(self, scout_step):
        candidates = _make_candidates(2)
        mock_source = AsyncMock()
        mock_source.fetch_candidates.return_value = candidates

        with patch("pipepost.steps.scout.get_source", return_value=mock_source):
            ctx = FlowContext(
                source_name="test_source",
                existing_urls={"https://example.com/0", "https://example.com/1"},
            )
            result = await scout_step.execute(ctx)

        assert result.has_errors
        assert "No new candidates found" in result.errors[0]
        assert result.candidates == []

    @pytest.mark.asyncio
    async def test_logs_candidate_counts(self, scout_step, caplog):
        candidates = _make_candidates(5)
        mock_source = AsyncMock()
        mock_source.fetch_candidates.return_value = candidates

        with patch("pipepost.steps.scout.get_source", return_value=mock_source):
            ctx = FlowContext(
                source_name="test_source",
                existing_urls={"https://example.com/0"},
            )
            with caplog.at_level(logging.INFO, logger="pipepost.steps.scout"):
                await scout_step.execute(ctx)

        assert "5 candidates fetched" in caplog.text
        assert "4 after filtering" in caplog.text


class TestScoutStepShouldSkip:
    def test_skips_when_no_source_name(self, scout_step):
        ctx = FlowContext(source_name="")
        assert scout_step.should_skip(ctx) is True

    def test_does_not_skip_when_source_name_present(self, scout_step):
        ctx = FlowContext(source_name="hackernews")
        assert scout_step.should_skip(ctx) is False
