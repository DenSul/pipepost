"""Tests for ValidateStep — min length, ratio, missing fields."""

from __future__ import annotations

import pytest

from pipepost.core.context import FlowContext, TranslatedArticle
from pipepost.steps.validate import ValidateStep


@pytest.fixture
def validate_step():
    return ValidateStep(min_content_len=300, min_ratio=0.3)


@pytest.fixture
def good_translated():
    return TranslatedArticle(
        title="Original",
        title_translated="Перевод",
        content="x" * 1000,
        content_translated="y" * 800,
        source_url="https://example.com/article",
        source_name="hackernews",
        tags=["python"],
    )


class TestValidateStepShouldSkip:
    def test_skips_when_no_translated(self, validate_step):
        ctx = FlowContext()
        assert validate_step.should_skip(ctx) is True

    def test_does_not_skip_with_translated(self, validate_step, good_translated):
        ctx = FlowContext()
        ctx.translated = good_translated
        assert validate_step.should_skip(ctx) is False


class TestValidateStepExecute:
    @pytest.mark.asyncio
    async def test_valid_article_passes(self, validate_step, good_translated):
        ctx = FlowContext()
        ctx.translated = good_translated
        result = await validate_step.execute(ctx)
        assert not result.has_errors

    @pytest.mark.asyncio
    async def test_missing_translated_title(self, validate_step, good_translated):
        good_translated.title_translated = ""
        ctx = FlowContext()
        ctx.translated = good_translated
        result = await validate_step.execute(ctx)
        assert result.has_errors
        assert any("title" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_content_too_short(self, validate_step):
        ctx = FlowContext()
        ctx.translated = TranslatedArticle(
            title="T",
            title_translated="П",
            content="x" * 1000,
            content_translated="y" * 50,  # way too short
            source_url="https://x.com",
        )
        result = await validate_step.execute(ctx)
        assert result.has_errors
        assert any("short" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_ratio_too_low(self, validate_step):
        ctx = FlowContext()
        ctx.translated = TranslatedArticle(
            title="T",
            title_translated="П",
            content="x" * 10000,
            content_translated="y" * 500,  # 5% ratio, below 30%
            source_url="https://x.com",
        )
        result = await validate_step.execute(ctx)
        assert result.has_errors
        assert any("ratio" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_missing_source_url(self, validate_step, good_translated):
        good_translated.source_url = ""
        ctx = FlowContext()
        ctx.translated = good_translated
        result = await validate_step.execute(ctx)
        assert result.has_errors
        assert any("source url" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_no_translated_adds_error(self, validate_step):
        ctx = FlowContext()
        ctx.translated = None
        # should_skip would normally prevent this, but test direct call
        result = await validate_step.execute(ctx)
        assert result.has_errors

    @pytest.mark.asyncio
    async def test_multiple_failures_accumulate(self):
        step = ValidateStep(min_content_len=1000, min_ratio=0.5)
        ctx = FlowContext()
        ctx.translated = TranslatedArticle(
            title="T",
            title_translated="",  # missing title
            content="x" * 5000,
            content_translated="y" * 100,  # too short + bad ratio
            source_url="",  # missing url
        )
        result = await step.execute(ctx)
        assert len(result.errors) >= 3
