"""Tests for AdaptStep — style adaptation, LLM mocking, output parsing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipepost.core.context import FlowContext, TranslatedArticle
from pipepost.steps.adapt import AdaptStep


@pytest.fixture
def adapt_step():
    return AdaptStep(model="test-model", style="blog", target_lang="ru")


@pytest.fixture
def ctx_with_translated():
    ctx = FlowContext(source_name="test")
    ctx.translated = TranslatedArticle(
        title="Original Title",
        title_translated="Переведённый заголовок",
        content="Original content here. " * 20,
        content_translated="Переведённый контент статьи. " * 20,
        source_url="https://example.com/art",
        source_name="test",
        tags=["python", "testing"],
    )
    return ctx


def _make_llm_response(text):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = text
    return mock_response


ADAPTED_GOOD_OUTPUT = (
    "===ADAPTED_TITLE===\n"
    "Адаптированный заголовок\n"
    "===ADAPTED_CONTENT===\n"
    "Адаптированный контент статьи для блога.\n"
)


class TestAdaptStepExecute:
    @pytest.mark.asyncio
    async def test_adapts_for_blog_style(self, adapt_step, ctx_with_translated):
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = _make_llm_response(ADAPTED_GOOD_OUTPUT)
            ctx = await adapt_step.execute(ctx_with_translated)

        assert ctx.metadata.get("adapted_title") == "Адаптированный заголовок"
        assert ctx.metadata.get("adapted_content") == "Адаптированный контент статьи для блога."

    @pytest.mark.asyncio
    async def test_adapts_for_telegram_style(self, ctx_with_translated):
        step = AdaptStep(model="test-model", style="telegram", target_lang="ru")
        prompt = step._build_prompt(ctx_with_translated.translated)
        assert "Telegram" in prompt
        assert "1000 characters" in prompt

    @pytest.mark.asyncio
    async def test_adapts_for_thread_style(self, ctx_with_translated):
        step = AdaptStep(model="test-model", style="thread", target_lang="ru")
        prompt = step._build_prompt(ctx_with_translated.translated)
        assert "Twitter/X thread" in prompt
        assert "280 chars" in prompt

    @pytest.mark.asyncio
    async def test_adapts_for_newsletter_style(self, ctx_with_translated):
        step = AdaptStep(model="test-model", style="newsletter", target_lang="ru")
        prompt = step._build_prompt(ctx_with_translated.translated)
        assert "newsletter" in prompt
        assert "Read more" in prompt

    @pytest.mark.asyncio
    async def test_does_not_overwrite_translated(self, adapt_step, ctx_with_translated):
        original_translated = ctx_with_translated.translated
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = _make_llm_response(ADAPTED_GOOD_OUTPUT)
            ctx = await adapt_step.execute(ctx_with_translated)

        assert ctx.translated is original_translated
        assert ctx.translated.title_translated == "Переведённый заголовок"

    @pytest.mark.asyncio
    async def test_stores_in_metadata(self, adapt_step, ctx_with_translated):
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = _make_llm_response(ADAPTED_GOOD_OUTPUT)
            ctx = await adapt_step.execute(ctx_with_translated)

        assert "adapted_title" in ctx.metadata
        assert "adapted_content" in ctx.metadata

    @pytest.mark.asyncio
    async def test_llm_failure_raises_translate_error(self, adapt_step, ctx_with_translated):
        from pipepost.exceptions import TranslateError

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.side_effect = RuntimeError("API down")
            with pytest.raises(TranslateError, match="LLM call failed"):
                await adapt_step.execute(ctx_with_translated)


class TestAdaptStepShouldSkip:
    def test_skips_when_no_translated(self, adapt_step):
        ctx = FlowContext()
        assert adapt_step.should_skip(ctx) is True

    def test_does_not_skip_when_translated_present(self, adapt_step, ctx_with_translated):
        assert adapt_step.should_skip(ctx_with_translated) is False


class TestBuildPrompt:
    def test_prompt_contains_style_instruction(self, ctx_with_translated):
        step = AdaptStep(model="test-model", style="blog", target_lang="ru")
        prompt = step._build_prompt(ctx_with_translated.translated)
        assert "blog post" in prompt
        assert "headers" in prompt

    def test_prompt_contains_target_lang(self, ctx_with_translated):
        step = AdaptStep(model="test-model", style="blog", target_lang="en")
        prompt = step._build_prompt(ctx_with_translated.translated)
        assert "Output in en" in prompt

    def test_prompt_contains_markers(self, ctx_with_translated):
        step = AdaptStep(model="test-model", style="blog", target_lang="ru")
        prompt = step._build_prompt(ctx_with_translated.translated)
        assert "===ADAPTED_TITLE===" in prompt
        assert "===ADAPTED_CONTENT===" in prompt


class TestParseOutput:
    def test_parse_output_valid(self, adapt_step):
        raw = "===ADAPTED_TITLE===\nНовый заголовок\n===ADAPTED_CONTENT===\nНовый контент\n"
        result = adapt_step._parse_output(raw)
        assert result is not None
        assert result["adapted_title"] == "Новый заголовок"
        assert result["adapted_content"] == "Новый контент"

    def test_parse_output_invalid_returns_none(self, adapt_step):
        raw = "Garbage output with no markers"
        result = adapt_step._parse_output(raw)
        assert result is None

    def test_parse_strips_thinking_tags(self, adapt_step):
        raw = (
            "<think>Let me think about this...</think>\n"
            "===ADAPTED_TITLE===\nЗаголовок\n"
            "===ADAPTED_CONTENT===\nСодержание\n"
        )
        result = adapt_step._parse_output(raw)
        assert result is not None
        assert result["adapted_title"] == "Заголовок"
        assert result["adapted_content"] == "Содержание"

    def test_parse_missing_title_returns_empty_string(self, adapt_step):
        raw = "===ADAPTED_CONTENT===\nСодержание\n"
        result = adapt_step._parse_output(raw)
        assert result is not None
        assert result["adapted_title"] == ""
