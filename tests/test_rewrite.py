"""Tests for RewriteStep."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipepost.core.context import Article, FlowContext, TranslatedArticle
from pipepost.core.step import StepBuildContext
from pipepost.exceptions import RewriteError
from pipepost.steps.rewrite import RewriteStep


@pytest.fixture()
def step() -> RewriteStep:
    return RewriteStep(model="test/model", creativity=0.7)


@pytest.fixture()
def ctx_with_translated() -> FlowContext:
    ctx = FlowContext(source_name="test")
    ctx.translated = TranslatedArticle(
        title="Original Title",
        title_translated="Переведённый заголовок",
        content="Original content in English.",
        content_translated="Переведённый контент на русском языке.",
        source_url="https://example.com/article",
        source_name="test",
        tags=["ai", "tech"],
    )
    return ctx


@pytest.fixture()
def ctx_with_selected() -> FlowContext:
    ctx = FlowContext(source_name="test")
    ctx.selected = Article(
        url="https://example.com/article",
        title="Selected Article Title",
        content="Full content of the selected article for rewriting.",
    )
    return ctx


@pytest.fixture()
def ctx_empty() -> FlowContext:
    return FlowContext(source_name="test")


class TestRewriteStepExecute:
    """Tests for RewriteStep.execute()."""

    @pytest.mark.asyncio()
    async def test_rewrite_translated_article(
        self, step: RewriteStep, ctx_with_translated: FlowContext
    ) -> None:
        llm_output = (
            "===TITLE_REWRITTEN===\nПолностью новый заголовок\n"
            "===CONTENT_REWRITTEN===\nПолностью переписанный контент."
        )
        with patch.object(step, "_call_llm", new_callable=AsyncMock, return_value=llm_output):
            result = await step.execute(ctx_with_translated)

        assert result.translated is not None
        assert result.translated.title_translated == "Полностью новый заголовок"
        assert result.translated.content_translated == "Полностью переписанный контент."
        # Original fields preserved
        assert result.translated.title == "Original Title"
        assert result.translated.content == "Original content in English."
        assert result.translated.tags == ["ai", "tech"]

    @pytest.mark.asyncio()
    async def test_rewrite_selected_article(
        self, step: RewriteStep, ctx_with_selected: FlowContext
    ) -> None:
        llm_output = (
            "===TITLE_REWRITTEN===\nRewritten Article Title\n"
            "===CONTENT_REWRITTEN===\nCompletely rewritten article content."
        )
        with patch.object(step, "_call_llm", new_callable=AsyncMock, return_value=llm_output):
            result = await step.execute(ctx_with_selected)

        assert result.translated is not None
        assert result.translated.title_translated == "Rewritten Article Title"
        assert result.translated.content_translated == "Completely rewritten article content."
        assert result.translated.source_url == "https://example.com/article"

    @pytest.mark.asyncio()
    async def test_rewrite_empty_context(
        self, step: RewriteStep, ctx_empty: FlowContext
    ) -> None:
        result = await step.execute(ctx_empty)
        assert result.translated is None
        assert "No article to rewrite" in result.errors

    @pytest.mark.asyncio()
    async def test_rewrite_parse_failure_raises(
        self, step: RewriteStep, ctx_with_translated: FlowContext
    ) -> None:
        with (
            patch.object(
                step, "_call_llm", new_callable=AsyncMock, return_value="garbage output"
            ),
            pytest.raises(RewriteError, match="Failed to parse rewrite output"),
        ):
            await step.execute(ctx_with_translated)

    @pytest.mark.asyncio()
    async def test_rewrite_llm_failure_raises(
        self, step: RewriteStep, ctx_with_translated: FlowContext
    ) -> None:
        with (
            patch.object(
                step,
                "_call_llm",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API down"),
            ),
            pytest.raises(RewriteError, match="LLM call failed"),
        ):
            await step.execute(ctx_with_translated)


class TestRewriteStepShouldSkip:
    """Tests for RewriteStep.should_skip()."""

    def test_skip_when_empty(self, step: RewriteStep, ctx_empty: FlowContext) -> None:
        assert step.should_skip(ctx_empty) is True

    def test_no_skip_with_translated(
        self, step: RewriteStep, ctx_with_translated: FlowContext
    ) -> None:
        assert step.should_skip(ctx_with_translated) is False

    def test_no_skip_with_selected(
        self, step: RewriteStep, ctx_with_selected: FlowContext
    ) -> None:
        assert step.should_skip(ctx_with_selected) is False


class TestRewriteStepFromConfig:
    """Tests for RewriteStep.from_config()."""

    def test_from_config_defaults(self) -> None:
        build_ctx = StepBuildContext()
        step = RewriteStep.from_config(build_ctx)
        assert step.creativity == 0.7
        assert step.target_lang == "ru"

    def test_from_config_custom(self) -> None:
        build_ctx = StepBuildContext(
            rewrite_model="openai/gpt-4o",
            rewrite_creativity=0.9,
            target_lang="en",
        )
        step = RewriteStep.from_config(build_ctx)
        assert step.model == "openai/gpt-4o"
        assert step.creativity == 0.9
        assert step.target_lang == "en"

    def test_from_config_falls_back_to_translate_model(self) -> None:
        build_ctx = StepBuildContext(model="anthropic/claude-3-haiku")
        step = RewriteStep.from_config(build_ctx)
        assert step.model == "anthropic/claude-3-haiku"


class TestRewriteStepParseOutput:
    """Tests for RewriteStep._parse_output()."""

    def test_parse_valid(self, step: RewriteStep) -> None:
        raw = (
            "===TITLE_REWRITTEN===\nNew title\n"
            "===CONTENT_REWRITTEN===\nNew content here."
        )
        result = step._parse_output(raw)
        assert result is not None
        assert result["title_rewritten"] == "New title"
        assert result["content_rewritten"] == "New content here."

    def test_parse_strips_think_tags(self, step: RewriteStep) -> None:
        raw = (
            "<think>thinking about rewrite...</think>"
            "===TITLE_REWRITTEN===\nClean title\n"
            "===CONTENT_REWRITTEN===\nClean content."
        )
        result = step._parse_output(raw)
        assert result is not None
        assert result["title_rewritten"] == "Clean title"

    def test_parse_missing_content_returns_none(self, step: RewriteStep) -> None:
        raw = "===TITLE_REWRITTEN===\nOnly title, no content"
        result = step._parse_output(raw)
        assert result is None

    def test_parse_garbage_returns_none(self, step: RewriteStep) -> None:
        result = step._parse_output("Just some random text without markers")
        assert result is None


class TestRewriteStepBuildPrompt:
    """Tests for RewriteStep._build_prompt()."""

    def test_prompt_contains_title_and_content(self, step: RewriteStep) -> None:
        prompt = step._build_prompt("Test Title", "Test content body")
        assert "Test Title" in prompt
        assert "Test content body" in prompt
        assert "TITLE_REWRITTEN" in prompt
        assert "CONTENT_REWRITTEN" in prompt
        assert "plagiarism" in prompt.lower()
