"""Tests for DeduplicationStep and PostPublishStep."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pipepost.core.context import Article, FlowContext, PublishResult
from pipepost.steps.dedup import DeduplicationStep, PostPublishStep


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.load_existing_urls.return_value = {
        "https://seen.com/1",
        "https://seen.com/2",
    }
    return storage


@pytest.fixture
def empty_storage():
    storage = MagicMock()
    storage.load_existing_urls.return_value = set()
    return storage


class TestDeduplicationStep:
    @pytest.mark.asyncio
    async def test_loads_existing_urls_into_context(self, mock_storage):
        step = DeduplicationStep(storage=mock_storage)
        ctx = FlowContext()
        result = await step.execute(ctx)
        assert result.existing_urls == {"https://seen.com/1", "https://seen.com/2"}
        mock_storage.load_existing_urls.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_storage_sets_empty_set(self, empty_storage):
        step = DeduplicationStep(storage=empty_storage)
        ctx = FlowContext()
        result = await step.execute(ctx)
        assert result.existing_urls == set()

    def test_never_skips(self, mock_storage):
        step = DeduplicationStep(storage=mock_storage)
        ctx = FlowContext()
        assert step.should_skip(ctx) is False


class TestPostPublishStep:
    @pytest.mark.asyncio
    async def test_marks_published_url(self, mock_storage):
        step = PostPublishStep(storage=mock_storage)
        ctx = FlowContext(
            selected=Article(url="https://new.com/art", title="Art", content="body"),
            published=PublishResult(success=True, slug="art-slug"),
            source_name="rss",
        )
        await step.execute(ctx)
        mock_storage.mark_published.assert_called_once_with(
            url="https://new.com/art",
            source_name="rss",
            slug="art-slug",
        )

    def test_skips_when_no_published(self, mock_storage):
        step = PostPublishStep(storage=mock_storage)
        ctx = FlowContext()
        assert step.should_skip(ctx) is True

    def test_skips_when_publish_failed(self, mock_storage):
        step = PostPublishStep(storage=mock_storage)
        ctx = FlowContext(published=PublishResult(success=False, error="fail"))
        assert step.should_skip(ctx) is True

    def test_does_not_skip_when_success(self, mock_storage):
        step = PostPublishStep(storage=mock_storage)
        ctx = FlowContext(published=PublishResult(success=True, slug="ok"))
        assert step.should_skip(ctx) is False
