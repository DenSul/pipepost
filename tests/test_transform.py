"""Tests for TransformStep (fused translate+rewrite+adapt)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from pipepost.core.context import Article, FlowContext
from pipepost.core.step import StepBuildContext
from pipepost.exceptions import TranslateError
from pipepost.steps.transform import TransformStep


@pytest.fixture()
def ctx_with_article() -> FlowContext:
    ctx = FlowContext(source_name="test")
    ctx.selected = Article(
        url="https://example.com/article",
        title="Original Title",
        content="Full content of the article for processing.",
        cover_image="https://example.com/cover.jpg",
    )
    return ctx


@pytest.fixture()
def ctx_empty() -> FlowContext:
    return FlowContext(source_name="test")


LLM_OUTPUT = (
    "===TITLE===\nНовый заголовок\n"
    "===CONTENT===\nПолностью обработанный контент.\n"
    "===TAGS===\nai, tech, python"
)


class TestTransformTranslateOnly:
    """Test transform with translate only (default)."""

    @pytest.mark.asyncio()
    async def test_translate_only(self, ctx_with_article: FlowContext) -> None:
        step = TransformStep(model="test/model", do_translate=True)
        with patch.object(step, "_call_llm", new_callable=AsyncMock, return_value=LLM_OUTPUT):
            result = await step.execute(ctx_with_article)

        assert result.translated is not None
        assert result.translated.title_translated == "Новый заголовок"
        assert result.translated.content_translated == "Полностью обработанный контент."
        assert result.translated.tags == ["ai", "tech", "python"]
        assert result.translated.source_url == "https://example.com/article"
        assert result.translated.cover_image == "https://example.com/cover.jpg"

    @pytest.mark.asyncio()
    async def test_translate_prompt_contains_translate(
        self, ctx_with_article: FlowContext
    ) -> None:
        step = TransformStep(model="test/model", do_translate=True, target_lang="ru")
        with patch.object(step, "_call_llm", new_callable=AsyncMock, return_value=LLM_OUTPUT) as mock:
            await step.execute(ctx_with_article)

        prompt = mock.call_args[0][0]
        assert "TRANSLATE" in prompt
        assert "ru" in prompt
        assert "REWRITE" not in prompt
        assert "ADAPT" not in prompt


class TestTransformRewriteOnly:
    """Test transform with rewrite only."""

    @pytest.mark.asyncio()
    async def test_rewrite_only(self, ctx_with_article: FlowContext) -> None:
        step = TransformStep(model="test/model", do_translate=False, do_rewrite=True)
        with patch.object(step, "_call_llm", new_callable=AsyncMock, return_value=LLM_OUTPUT):
            result = await step.execute(ctx_with_article)

        assert result.translated is not None
        assert result.translated.title_translated == "Новый заголовок"

    @pytest.mark.asyncio()
    async def test_rewrite_prompt_contains_rewrite(
        self, ctx_with_article: FlowContext
    ) -> None:
        step = TransformStep(model="test/model", do_translate=False, do_rewrite=True)
        with patch.object(step, "_call_llm", new_callable=AsyncMock, return_value=LLM_OUTPUT) as mock:
            await step.execute(ctx_with_article)

        prompt = mock.call_args[0][0]
        assert "REWRITE" in prompt
        assert "plagiarism" in prompt.lower()
        assert "TRANSLATE" not in prompt


class TestTransformCombined:
    """Test combined translate+rewrite+adapt."""

    @pytest.mark.asyncio()
    async def test_all_three(self, ctx_with_article: FlowContext) -> None:
        step = TransformStep(
            model="test/model",
            do_translate=True,
            do_rewrite=True,
            do_adapt=True,
            style="telegram",
        )
        with patch.object(step, "_call_llm", new_callable=AsyncMock, return_value=LLM_OUTPUT) as mock:
            result = await step.execute(ctx_with_article)

        prompt = mock.call_args[0][0]
        assert "TRANSLATE" in prompt
        assert "REWRITE" in prompt
        assert "ADAPT" in prompt
        assert "telegram" in prompt.lower()

        assert result.translated is not None
        assert result.metadata.get("adapted_title") == "Новый заголовок"
        assert result.metadata.get("adapted_content") == "Полностью обработанный контент."

    @pytest.mark.asyncio()
    async def test_translate_plus_rewrite(self, ctx_with_article: FlowContext) -> None:
        step = TransformStep(
            model="test/model", do_translate=True, do_rewrite=True
        )
        with patch.object(step, "_call_llm", new_callable=AsyncMock, return_value=LLM_OUTPUT) as mock:
            await step.execute(ctx_with_article)

        prompt = mock.call_args[0][0]
        assert "TRANSLATE" in prompt
        assert "REWRITE" in prompt
        assert "translated text" in prompt.lower()


class TestTransformShouldSkip:
    """Tests for should_skip."""

    def test_skip_when_empty(self, ctx_empty: FlowContext) -> None:
        step = TransformStep(model="test/model")
        assert step.should_skip(ctx_empty) is True

    def test_no_skip_with_article(self, ctx_with_article: FlowContext) -> None:
        step = TransformStep(model="test/model")
        assert step.should_skip(ctx_with_article) is False


class TestTransformErrors:
    """Test error handling."""

    @pytest.mark.asyncio()
    async def test_parse_failure_raises(self, ctx_with_article: FlowContext) -> None:
        step = TransformStep(model="test/model")
        with (
            patch.object(step, "_call_llm", new_callable=AsyncMock, return_value="garbage"),
            pytest.raises(TranslateError, match="Failed to parse"),
        ):
            await step.execute(ctx_with_article)

    @pytest.mark.asyncio()
    async def test_llm_failure_raises(self, ctx_with_article: FlowContext) -> None:
        step = TransformStep(model="test/model")
        with (
            patch.object(
                step, "_call_llm", new_callable=AsyncMock,
                side_effect=RuntimeError("API down"),
            ),
            pytest.raises(TranslateError, match="Transform LLM call failed"),
        ):
            await step.execute(ctx_with_article)

    @pytest.mark.asyncio()
    async def test_empty_context_adds_error(self, ctx_empty: FlowContext) -> None:
        step = TransformStep(model="test/model")
        result = await step.execute(ctx_empty)
        assert "No article to transform" in result.errors


class TestTransformFromConfig:
    """Tests for from_config."""

    def test_defaults(self) -> None:
        build_ctx = StepBuildContext()
        step = TransformStep.from_config(build_ctx)
        assert step.do_translate is True
        assert step.do_rewrite is False
        assert step.do_adapt is False
        assert step.style == "blog"

    def test_custom(self) -> None:
        build_ctx = StepBuildContext(
            transform_model="openai/gpt-4o",
            transform_translate=True,
            transform_rewrite=True,
            transform_adapt=True,
            transform_style="telegram",
            transform_creativity=0.8,
        )
        step = TransformStep.from_config(build_ctx)
        assert step.model == "openai/gpt-4o"
        assert step.do_translate is True
        assert step.do_rewrite is True
        assert step.do_adapt is True
        assert step.style == "telegram"
        assert step.creativity == 0.8


class TestTransformParseOutput:
    """Tests for _parse_output."""

    def test_parse_valid(self) -> None:
        step = TransformStep(model="test/model")
        result = step._parse_output(LLM_OUTPUT)
        assert result is not None
        assert result["title"] == "Новый заголовок"
        assert result["content"] == "Полностью обработанный контент."
        assert result["tags"] == ["ai", "tech", "python"]

    def test_parse_strips_think_tags(self) -> None:
        step = TransformStep(model="test/model")
        raw = "<think>hmm</think>" + LLM_OUTPUT
        result = step._parse_output(raw)
        assert result is not None
        assert result["title"] == "Новый заголовок"

    def test_parse_no_content_returns_none(self) -> None:
        step = TransformStep(model="test/model")
        result = step._parse_output("===TITLE===\nOnly title")
        assert result is None

    def test_parse_garbage_returns_none(self) -> None:
        step = TransformStep(model="test/model")
        result = step._parse_output("random text")
        assert result is None


class TestTransformPromptDynamic:
    """Test that prompt adapts to enabled operations."""

    def test_no_operations(self) -> None:
        step = TransformStep(
            model="test/model", do_translate=False, do_rewrite=False, do_adapt=False
        )
        prompt = step._build_prompt("Title", "Content")
        assert "meaning" in prompt.lower()
        assert "TITLE" in prompt

    def test_all_operations(self) -> None:
        step = TransformStep(
            model="test/model",
            do_translate=True,
            do_rewrite=True,
            do_adapt=True,
            style="newsletter",
            target_lang="de",
        )
        prompt = step._build_prompt("Title", "Content")
        assert "TRANSLATE" in prompt
        assert "de" in prompt
        assert "REWRITE" in prompt
        assert "ADAPT" in prompt
        assert "newsletter" in prompt
        assert "\u2192" in prompt
