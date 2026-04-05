"""Tests for FanoutPublishStep — multi-destination concurrent publishing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from pipepost.core.context import FlowContext, PublishResult, TranslatedArticle
from pipepost.steps.fanout import FanoutPublishStep


@pytest.fixture
def good_translated():
    return TranslatedArticle(
        title="Original",
        title_translated="Translated",
        content="English content",
        content_translated="Translated content",
        source_url="https://example.com/art",
        source_name="hackernews",
        tags=["python"],
    )


def _make_mock_dest(name, result=None, side_effect=None):
    """Create a mock destination with the given publish result or side effect."""
    dest = AsyncMock()
    dest.name = name
    if side_effect is not None:
        dest.publish.side_effect = side_effect
    elif result is not None:
        dest.publish.return_value = result
    else:
        dest.publish.return_value = PublishResult(
            success=True, slug=f"{name}-slug", url=f"/{name}-slug"
        )
    return dest


class TestFanoutShouldSkip:
    def test_skips_when_no_translated(self):
        step = FanoutPublishStep(destination_names=["a", "b"])
        ctx = FlowContext()
        assert step.should_skip(ctx) is True

    def test_skips_when_has_errors(self, good_translated):
        step = FanoutPublishStep(destination_names=["a"])
        ctx = FlowContext(translated=good_translated)
        ctx.add_error("previous error")
        assert step.should_skip(ctx) is True

    def test_skips_in_dry_run(self, good_translated):
        step = FanoutPublishStep(destination_names=["a"])
        ctx = FlowContext(translated=good_translated, metadata={"dry_run": True})
        assert step.should_skip(ctx) is True

    def test_does_not_skip_when_ready(self, good_translated):
        step = FanoutPublishStep(destination_names=["a"])
        ctx = FlowContext(translated=good_translated)
        assert step.should_skip(ctx) is False


class TestFanoutExecute:
    @pytest.mark.asyncio
    async def test_publishes_to_multiple_destinations(self, good_translated, monkeypatch):
        dest_a = _make_mock_dest("a")
        dest_b = _make_mock_dest("b")

        def _get(name):
            return {"a": dest_a, "b": dest_b}[name]

        monkeypatch.setattr("pipepost.core.registry.get_destination", _get)

        step = FanoutPublishStep(destination_names=["a", "b"])
        ctx = FlowContext(translated=good_translated)
        result = await step.execute(ctx)

        dest_a.publish.assert_awaited_once_with(good_translated)
        dest_b.publish.assert_awaited_once_with(good_translated)
        assert not result.has_errors

    @pytest.mark.asyncio
    async def test_collects_all_results_in_metadata(self, good_translated, monkeypatch):
        dest_a = _make_mock_dest("a")
        dest_b = _make_mock_dest(
            "b",
            result=PublishResult(success=False, error="timeout"),
        )

        def _get(name):
            return {"a": dest_a, "b": dest_b}[name]

        monkeypatch.setattr("pipepost.core.registry.get_destination", _get)

        step = FanoutPublishStep(destination_names=["a", "b"])
        ctx = FlowContext(translated=good_translated)
        result = await step.execute(ctx)

        fanout = result.metadata["fanout_results"]
        assert isinstance(fanout, dict)
        assert fanout["a"]["success"] is True
        assert fanout["a"]["slug"] == "a-slug"
        assert fanout["b"]["success"] is False
        assert fanout["b"]["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_sets_published_to_first_success(self, good_translated, monkeypatch):
        result_a = PublishResult(success=True, slug="first-slug", url="/first")
        result_b = PublishResult(success=True, slug="second-slug", url="/second")
        dest_a = _make_mock_dest("a", result=result_a)
        dest_b = _make_mock_dest("b", result=result_b)

        def _get(name):
            return {"a": dest_a, "b": dest_b}[name]

        monkeypatch.setattr("pipepost.core.registry.get_destination", _get)

        step = FanoutPublishStep(destination_names=["a", "b"])
        ctx = FlowContext(translated=good_translated)
        result = await step.execute(ctx)

        # First successful result (order of destination_names)
        assert result.published is not None
        assert result.published.slug == "first-slug"

    @pytest.mark.asyncio
    async def test_continues_on_error_by_default(self, good_translated, monkeypatch):
        dest_a = _make_mock_dest("a", side_effect=RuntimeError("boom"))
        dest_b = _make_mock_dest("b")

        def _get(name):
            return {"a": dest_a, "b": dest_b}[name]

        monkeypatch.setattr("pipepost.core.registry.get_destination", _get)

        step = FanoutPublishStep(destination_names=["a", "b"])
        ctx = FlowContext(translated=good_translated)
        result = await step.execute(ctx)

        dest_a.publish.assert_awaited_once()
        dest_b.publish.assert_awaited_once()
        # stop_on_first_error=False → no errors added to ctx
        assert not result.has_errors
        assert result.published is not None
        assert result.published.slug == "b-slug"

    @pytest.mark.asyncio
    async def test_stops_on_first_error_when_configured(self, good_translated, monkeypatch):
        dest_a = _make_mock_dest(
            "a",
            result=PublishResult(success=False, error="fail"),
        )
        dest_b = _make_mock_dest("b")

        def _get(name):
            return {"a": dest_a, "b": dest_b}[name]

        monkeypatch.setattr("pipepost.core.registry.get_destination", _get)

        step = FanoutPublishStep(destination_names=["a", "b"], stop_on_first_error=True)
        ctx = FlowContext(translated=good_translated)
        result = await step.execute(ctx)

        # Both called (concurrent), but errors are added to ctx
        dest_a.publish.assert_awaited_once()
        dest_b.publish.assert_awaited_once()
        assert result.has_errors
        assert any("fail" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_no_article_adds_error(self, monkeypatch):
        step = FanoutPublishStep(destination_names=["a"])
        ctx = FlowContext()
        ctx.translated = None
        result = await step.execute(ctx)
        assert result.has_errors
        assert "No article" in result.errors[0]

    @pytest.mark.asyncio
    async def test_unknown_destination_adds_error(self, good_translated, monkeypatch):
        dest_b = _make_mock_dest("b")

        def _get(name):
            if name == "b":
                return dest_b
            msg = f"Destination '{name}' not registered."
            raise KeyError(msg)

        monkeypatch.setattr("pipepost.core.registry.get_destination", _get)

        step = FanoutPublishStep(destination_names=["bad_name", "b"])
        ctx = FlowContext(translated=good_translated)
        result = await step.execute(ctx)

        # Unknown dest logged as error, but "b" still published
        assert any("Unknown destination" in e for e in result.errors)
        dest_b.publish.assert_awaited_once()
        assert result.published is not None

    @pytest.mark.asyncio
    async def test_concurrent_execution(self, good_translated, monkeypatch):
        """Verify destinations are called concurrently, not sequentially."""
        call_times = []

        async def _slow_publish(article):
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.05)
            return PublishResult(success=True, slug="ok", url="/ok")

        dest_a = AsyncMock()
        dest_a.name = "a"
        dest_a.publish.side_effect = _slow_publish

        dest_b = AsyncMock()
        dest_b.name = "b"
        dest_b.publish.side_effect = _slow_publish

        def _get(name):
            return {"a": dest_a, "b": dest_b}[name]

        monkeypatch.setattr("pipepost.core.registry.get_destination", _get)

        step = FanoutPublishStep(destination_names=["a", "b"])
        ctx = FlowContext(translated=good_translated)
        await step.execute(ctx)

        # Both should start within a tiny window (concurrent), not 50ms apart
        assert len(call_times) == 2
        assert abs(call_times[0] - call_times[1]) < 0.03

    @pytest.mark.asyncio
    async def test_all_destinations_fail(self, good_translated, monkeypatch):
        dest_a = _make_mock_dest(
            "a",
            result=PublishResult(success=False, error="fail-a"),
        )
        dest_b = _make_mock_dest(
            "b",
            result=PublishResult(success=False, error="fail-b"),
        )

        def _get(name):
            return {"a": dest_a, "b": dest_b}[name]

        monkeypatch.setattr("pipepost.core.registry.get_destination", _get)

        step = FanoutPublishStep(destination_names=["a", "b"])
        ctx = FlowContext(translated=good_translated)
        result = await step.execute(ctx)

        assert result.published is None
        fanout = result.metadata["fanout_results"]
        assert fanout["a"]["success"] is False
        assert fanout["b"]["success"] is False
