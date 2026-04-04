"""Tests for PublishStep — destination mocking, error handling."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pipepost.core.context import FlowContext, PublishResult, TranslatedArticle
from pipepost.steps.publish import PublishStep


@pytest.fixture
def good_translated():
    return TranslatedArticle(
        title="Original",
        title_translated="Перевод",
        content="English content",
        content_translated="Русский контент",
        source_url="https://example.com/art",
        source_name="hackernews",
        tags=["python"],
    )


class TestPublishStepShouldSkip:
    def test_skips_when_no_translated(self):
        step = PublishStep(destination_name="test")
        ctx = FlowContext()
        assert step.should_skip(ctx) is True

    def test_skips_when_has_errors(self, good_translated):
        step = PublishStep(destination_name="test")
        ctx = FlowContext()
        ctx.translated = good_translated
        ctx.add_error("previous error")
        assert step.should_skip(ctx) is True

    def test_does_not_skip_when_ready(self, good_translated):
        step = PublishStep(destination_name="test")
        ctx = FlowContext()
        ctx.translated = good_translated
        assert step.should_skip(ctx) is False


class TestPublishStepExecute:
    @pytest.mark.asyncio
    async def test_successful_publish(self, good_translated, monkeypatch):
        mock_dest = AsyncMock()
        mock_dest.publish.return_value = PublishResult(
            success=True, slug="my-article", url="/out/my-article.md",
        )

        # get_destination is imported inside execute via `from pipepost.core.registry import get_destination`
        monkeypatch.setattr(
            "pipepost.core.registry.get_destination",
            lambda name: mock_dest,
        )

        step = PublishStep(destination_name="mock")
        ctx = FlowContext()
        ctx.translated = good_translated
        result = await step.execute(ctx)

        assert result.published is not None
        assert result.published.success is True
        assert result.published.slug == "my-article"
        assert not result.has_errors

    @pytest.mark.asyncio
    async def test_publish_failure_result(self, good_translated, monkeypatch):
        mock_dest = AsyncMock()
        mock_dest.publish.return_value = PublishResult(
            success=False, error="webhook returned 500",
        )

        monkeypatch.setattr(
            "pipepost.core.registry.get_destination",
            lambda name: mock_dest,
        )

        step = PublishStep(destination_name="mock")
        ctx = FlowContext()
        ctx.translated = good_translated
        result = await step.execute(ctx)

        assert result.has_errors
        assert "webhook returned 500" in result.errors[0]

    @pytest.mark.asyncio
    async def test_publish_exception(self, good_translated, monkeypatch):
        mock_dest = AsyncMock()
        mock_dest.publish.side_effect = RuntimeError("connection refused")

        monkeypatch.setattr(
            "pipepost.core.registry.get_destination",
            lambda name: mock_dest,
        )

        step = PublishStep(destination_name="mock")
        ctx = FlowContext()
        ctx.translated = good_translated
        result = await step.execute(ctx)

        assert result.has_errors
        assert result.published is not None
        assert result.published.success is False
        assert "connection refused" in result.published.error

    @pytest.mark.asyncio
    async def test_no_article_adds_error(self, monkeypatch):
        monkeypatch.setattr(
            "pipepost.core.registry.get_destination",
            lambda name: AsyncMock(),
        )

        step = PublishStep(destination_name="mock")
        ctx = FlowContext()
        ctx.translated = None
        result = await step.execute(ctx)
        assert result.has_errors
        assert "No article" in result.errors[0]
