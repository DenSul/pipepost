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
    "Это переведённый контент статьи. Ещё текст для длины. " * 10 + "\n===TAGS===\n"
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
    async def test_llm_failure_raises_translate_error(self, translate_step, ctx_with_article):
        from pipepost.exceptions import TranslateError

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.side_effect = RuntimeError("API down")
            with pytest.raises(TranslateError, match="LLM call failed"):
                await translate_step.execute(ctx_with_article)

        assert ctx_with_article.translated is None

    @pytest.mark.asyncio
    async def test_bad_output_parse_raises_translate_error(self, translate_step, ctx_with_article):
        from pipepost.exceptions import TranslateError

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = _make_llm_response("Garbage output with no markers")
            with pytest.raises(TranslateError, match="parse"):
                await translate_step.execute(ctx_with_article)

    @pytest.mark.asyncio
    async def test_no_article_adds_error(self, translate_step):
        ctx = FlowContext()
        result = await translate_step.execute(ctx)
        assert result.has_errors
        assert "No article" in result.errors[0]

    @pytest.mark.asyncio
    async def test_retries_on_first_llm_failure(self, translate_step, ctx_with_article):
        """LLM is retried once on failure before raising."""
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.side_effect = [
                RuntimeError("transient"),
                _make_llm_response(LLM_GOOD_OUTPUT),
            ]
            ctx = await translate_step.execute(ctx_with_article)

        assert ctx.translated is not None
        assert mock_acomp.call_count == 2

    @pytest.mark.asyncio
    async def test_cover_image_propagated(self, translate_step):
        """Cover image from article is propagated to translated article."""
        ctx = FlowContext(source_name="test")
        ctx.selected = Article(
            url="https://example.com/art",
            title="Title",
            content="Content here. " * 50,
            cover_image="https://example.com/img.jpg",
        )
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = _make_llm_response(LLM_GOOD_OUTPUT)
            ctx = await translate_step.execute(ctx)

        assert ctx.translated is not None
        assert ctx.translated.cover_image == "https://example.com/img.jpg"

    @pytest.mark.asyncio
    async def test_source_name_propagated(self, translate_step, ctx_with_article):
        """source_name from context is propagated to translated article."""
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = _make_llm_response(LLM_GOOD_OUTPUT)
            ctx = await translate_step.execute(ctx_with_article)

        assert ctx.translated is not None
        assert ctx.translated.source_name == "hackernews"


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
        raw = (
            "===TITLE_RU===\nМой заголовок\n"
            "===CONTENT_RU===\nМой контент\n"
            "===TAGS===\npython, testing\n"
        )
        result = translate_step._parse_output(raw)
        assert result is not None
        assert result["title_translated"] == "Мой заголовок"
        assert result["content_translated"] == "Мой контент"
        assert "python" in result["tags"]
        assert "testing" in result["tags"]

    def test_parse_strips_thinking_tags(self, translate_step):
        raw = (
            "<think>Let me analyze...</think>\n"
            "===TITLE_RU===\nЗаголовок\n"
            "===CONTENT_RU===\nСодержание\n"
            "===TAGS===\ntech\n"
        )
        result = translate_step._parse_output(raw)
        assert result is not None
        assert result["title_translated"] == "Заголовок"
        assert result["content_translated"] == "Содержание"

    def test_parse_missing_content_returns_none(self, translate_step):
        bad = "===TITLE_RU===\nSome title\n===TAGS===\ntech\n"
        result = translate_step._parse_output(bad)
        assert result is None

    def test_parse_tags_comma_separated(self, translate_step):
        raw = "===TITLE_RU===\nT\n===CONTENT_RU===\nC\n===TAGS===\nai, python, devops\n"
        result = translate_step._parse_output(raw)
        assert result is not None
        assert result["tags"] == ["ai", "python", "devops"]

    def test_parse_no_tags_section_defaults_to_empty(self, translate_step):
        """When TAGS section is missing entirely, tags default to empty list."""
        raw = "===TITLE_RU===\nT\n===CONTENT_RU===\nC\n"
        result = translate_step._parse_output(raw)
        assert result is not None
        # sections.get("TAGS", "") returns "" -> split/filter yields []
        assert result["tags"] == []

    def test_parse_empty_tags_section(self, translate_step):
        """When TAGS section is present but empty, tags are empty list."""
        raw = "===TITLE_RU===\nT\n===CONTENT_RU===\nC\n===TAGS===\n\n"
        result = translate_step._parse_output(raw)
        assert result is not None
        assert result["tags"] == []

    def test_parse_missing_title_returns_empty_string(self, translate_step):
        """When TITLE_RU section is missing, title_translated is empty."""
        raw = "===CONTENT_RU===\nSome content\n===TAGS===\npython\n"
        result = translate_step._parse_output(raw)
        assert result is not None
        assert result["title_translated"] == ""

    def test_parse_multiline_content(self, translate_step):
        """Content with multiple paragraphs is preserved."""
        raw = (
            "===TITLE_RU===\nT\n"
            "===CONTENT_RU===\nLine one\n\nLine two\n\nLine three\n"
            "===TAGS===\ntest\n"
        )
        result = translate_step._parse_output(raw)
        assert result is not None
        assert "Line one" in result["content_translated"]
        assert "Line three" in result["content_translated"]

    def test_parse_tags_whitespace_handling(self, translate_step):
        """Tags with extra whitespace are trimmed and lowercased."""
        raw = "===TITLE_RU===\nT\n===CONTENT_RU===\nC\n===TAGS===\n  Python , TESTING ,  AI  \n"
        result = translate_step._parse_output(raw)
        assert result is not None
        assert result["tags"] == ["python", "testing", "ai"]


class TestFormattingPreservation:
    """Verify _parse_output preserves markdown formatting in translated content."""

    def test_preserves_headings_in_translation(self, translate_step):
        raw = (
            "===TITLE_RU===\nЗаголовок\n"
            "===CONTENT_RU===\n"
            "# Главный заголовок\n\n## Подзаголовок\n\n### Третий уровень\n\n"
            "Текст параграфа.\n"
            "===TAGS===\ntest\n"
        )
        result = translate_step._parse_output(raw)
        assert result is not None
        content = result["content_translated"]
        assert "# Главный заголовок" in content
        assert "## Подзаголовок" in content
        assert "### Третий уровень" in content

    def test_preserves_code_blocks_in_translation(self, translate_step):
        raw = (
            "===TITLE_RU===\nТитул\n"
            "===CONTENT_RU===\n"
            "Вот пример кода:\n\n"
            "```python\ndef hello():\n    print('Привет мир')\n```\n\n"
            "Конец примера.\n"
            "===TAGS===\npython\n"
        )
        result = translate_step._parse_output(raw)
        assert result is not None
        content = result["content_translated"]
        assert "```python" in content
        assert "def hello():" in content
        assert "```" in content

    def test_preserves_links_in_translation(self, translate_step):
        raw = (
            "===TITLE_RU===\nТитул\n"
            "===CONTENT_RU===\n"
            "Подробнее на [официальном сайте](https://docs.example.com).\n"
            "===TAGS===\ntest\n"
        )
        result = translate_step._parse_output(raw)
        assert result is not None
        content = result["content_translated"]
        assert "[официальном сайте](https://docs.example.com)" in content

    def test_preserves_images_in_translation(self, translate_step):
        raw = (
            "===TITLE_RU===\nТитул\n"
            "===CONTENT_RU===\n"
            "Диаграмма архитектуры:\n\n"
            "![Схема архитектуры](https://example.com/arch.png)\n"
            "===TAGS===\ntest\n"
        )
        result = translate_step._parse_output(raw)
        assert result is not None
        content = result["content_translated"]
        assert "![Схема архитектуры](https://example.com/arch.png)" in content

    def test_preserves_tables_in_translation(self, translate_step):
        raw = (
            "===TITLE_RU===\nТитул\n"
            "===CONTENT_RU===\n"
            "| Функция | Статус |\n"
            "| --- | --- |\n"
            "| Авторизация | Готово |\n"
            "| Кэширование | В процессе |\n"
            "===TAGS===\ntest\n"
        )
        result = translate_step._parse_output(raw)
        assert result is not None
        content = result["content_translated"]
        assert "| Функция | Статус |" in content
        assert "| --- | --- |" in content
        assert "| Авторизация | Готово |" in content

    def test_preserves_lists_in_translation(self, translate_step):
        raw = (
            "===TITLE_RU===\nТитул\n"
            "===CONTENT_RU===\n"
            "Ненумерованный список:\n\n"
            "* Первый пункт\n"
            "* Второй пункт\n\n"
            "Нумерованный список:\n\n"
            "1. Шаг один\n"
            "2. Шаг два\n"
            "===TAGS===\ntest\n"
        )
        result = translate_step._parse_output(raw)
        assert result is not None
        content = result["content_translated"]
        assert "* Первый пункт" in content
        assert "* Второй пункт" in content
        assert "1. Шаг один" in content
        assert "2. Шаг два" in content

    def test_full_formatted_article(self, translate_step):
        raw = (
            "===TITLE_RU===\nПолная статья с форматированием\n"
            "===CONTENT_RU===\n"
            "# Введение\n\n"
            "Это **жирный** и *курсивный* текст.\n\n"
            "## Примеры кода\n\n"
            "Используйте `переменная` для инициализации.\n\n"
            "```python\ndef приветствие(имя):\n    return f'Привет, {имя}'\n```\n\n"
            "### Ресурсы\n\n"
            "Посетите [документацию](https://docs.example.com) для деталей.\n\n"
            "![Диаграмма](https://example.com/diagram.png)\n\n"
            "> Знание — сила.\n\n"
            "* Преимущество первое\n"
            "* Преимущество второе\n\n"
            "1. Первый шаг\n"
            "2. Второй шаг\n\n"
            "| Колонка1 | Колонка2 |\n"
            "| --- | --- |\n"
            "| Значение1 | Значение2 |\n"
            "===TAGS===\npython, testing\n"
        )
        result = translate_step._parse_output(raw)
        assert result is not None
        content = result["content_translated"]
        # Headings
        assert "# Введение" in content
        assert "## Примеры кода" in content
        assert "### Ресурсы" in content
        # Bold/italic
        assert "**жирный**" in content
        assert "*курсивный*" in content
        # Inline code
        assert "`переменная`" in content
        # Code block
        assert "```python" in content
        assert "def приветствие(имя):" in content
        # Link
        assert "[документацию](https://docs.example.com)" in content
        # Image
        assert "![Диаграмма](https://example.com/diagram.png)" in content
        # Blockquote
        assert "> Знание — сила." in content
        # Lists
        assert "* Преимущество первое" in content
        assert "1. Первый шаг" in content
        # Table
        assert "| Колонка1 | Колонка2 |" in content
