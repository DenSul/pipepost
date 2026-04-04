"""Tests for TranslateStep — LLM mocking, prompt building, output parsing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipepost.core.context import Article, FlowContext
from pipepost.steps.translate import TranslateStep


@pytest.fixture
def translate_step():
    return TranslateStep(model="test-model", target_lang="ru")


@pytest.fixture
def ctx_with_article():
    ctx = FlowContext(source_name="hackernews")
    ctx.selected = Article(
        url="https://example.com/art",
        title="Original Title",
        content="This is a long original article. " * 50,
    )
    return ctx


def _make_llm_response(text: str) -> MagicMock:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = text
    return mock_response


LLM_GOOD_OUTPUT = (
    "===TITLE_RU===\n"
    "Переведённый заголовок\n"
    "===CONTENT_RU===\n"
    "Это переведённый контент статьи. Ещё текст для длины. " * 10
    + "\n===TAGS===\n"
    "python, testing, ai\n"
)


class TestTranslateStepExecute:
    @pytest.mark.asyncio
    async def test_successful_translation(self, translate_step, ctx_with_article):
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = _make_llm_response(LLM_GOOD_OUTPUT)
            ctx = await translate_step.execute(ctx_with_article)

        assert ctx.translated is not None
        assert ctx.translated.title_translated == "Переведённый заголовок"
        assert "python" in ctx.translated.tags

    @pytest.mark.asyncio
    async def test_llm_failure_adds_error(self, translate_step, ctx_with_article):
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.side_effect = RuntimeError("API down")
            ctx = await translate_step.execute(ctx_with_article)

        assert ctx.has_errors
        assert any("LLM call failed" in e for e in ctx.errors)
        assert ctx.translated is None

    @pytest.mark.asyncio
    async def test_bad_output_parse_adds_error(self, translate_step, ctx_with_article):
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = _make_llm_response("Garbage output with no markers")
            ctx = await translate_step.execute(ctx_with_article)

        assert ctx.has_errors
        assert any("parse" in e.lower() for e in ctx.errors)

    @pytest.mark.asyncio
    async def test_no_article_adds_error(self, translate_step):
        ctx = FlowContext()
        result = await translate_step.execute(ctx)
        assert result.has_errors
        assert "No article" in result.errors[0]


class TestTranslateStepShouldSkip:
    def test_skips_when_no_article(self, translate_step):
        ctx = FlowContext()
        assert translate_step.should_skip(ctx) is True

    def test_does_not_skip_when_article_present(self, translate_step, ctx_with_article):
        assert translate_step.should_skip(ctx_with_article) is False


class TestBuildPrompt:
    def test_prompt_contains_title_and_content(self, translate_step):
        prompt = translate_step._build_prompt("My Title", "My Content")
        assert "My Title" in prompt
        assert "My Content" in prompt

    def test_prompt_contains_markers(self, translate_step):
        prompt = translate_step._build_prompt("T", "C")
        assert "===TITLE_RU===" in prompt
        assert "===CONTENT_RU===" in prompt
        assert "===TAGS===" in prompt

    def test_prompt_truncates_long_content(self, translate_step):
        long = "x" * 20000
        prompt = translate_step._build_prompt("T", long)
        # Content truncated to 15000
        assert len(prompt) < 20000


class TestParseOutput:
    def test_parse_valid_output(self, translate_step):
        raw = "===TITLE_RU===\nМой заголовок\n===CONTENT_RU===\nМой контент\n===TAGS===\npython, testing\n"
        result = translate_step._parse_output(raw)
        assert result is not None
        assert result["title_ru"] == "Мой заголовок"
        assert result["content_ru"] == "Мой контент"
        assert "python" in result["tags"]
        assert "testing" in result["tags"]

    def test_parse_strips_thinking_tags(self, translate_step):
        raw = "<think>Let me analyze...</think>\n===TITLE_RU===\nЗаголовок\n===CONTENT_RU===\nСодержание\n===TAGS===\ntech\n"
        result = translate_step._parse_output(raw)
        assert result is not None
        assert result["title_ru"] == "Заголовок"
        assert result["content_ru"] == "Содержание"

    def test_parse_missing_content_returns_none(self, translate_step):
        bad = "===TITLE_RU===\nSome title\n===TAGS===\ntech\n"
        result = translate_step._parse_output(bad)
        assert result is None

    def test_parse_tags_comma_separated(self, translate_step):
        raw = "===TITLE_RU===\nT\n===CONTENT_RU===\nC\n===TAGS===\nai, python, devops\n"
        result = translate_step._parse_output(raw)
        assert result is not None
        assert result["tags"] == ["ai", "python", "devops"]

    def test_parse_no_tags_section_defaults_to_tech(self, translate_step):
        """When TAGS section is missing entirely, default is 'tech'."""
        raw = "===TITLE_RU===\nT\n===CONTENT_RU===\nC\n"
        result = translate_step._parse_output(raw)
        assert result is not None
        # sections.get("TAGS", "tech") returns "tech" when TAGS missing
        assert result["tags"] == ["tech"]
