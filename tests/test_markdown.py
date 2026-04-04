"""Tests for MarkdownDestination — real file writes to tmpdir."""

from __future__ import annotations

import pytest

from pipepost.core.context import TranslatedArticle
from pipepost.destinations.markdown import MarkdownDestination


@pytest.fixture
def translated():
    return TranslatedArticle(
        title="Original Title",
        title_translated="Переведённый заголовок",
        content="English content",
        content_translated="Русский контент для статьи",
        source_url="https://example.com/article",
        source_name="hackernews",
        tags=["python", "testing"],
        cover_image="https://example.com/cover.jpg",
    )


class TestMarkdownPublish:
    @pytest.mark.asyncio
    async def test_creates_file(self, tmp_path, translated):
        dest = MarkdownDestination(output_dir=str(tmp_path))
        result = await dest.publish(translated)
        assert result.success is True
        assert (tmp_path / f"{result.slug}.md").exists()

    @pytest.mark.asyncio
    async def test_file_contains_frontmatter(self, tmp_path, translated):
        dest = MarkdownDestination(output_dir=str(tmp_path))
        result = await dest.publish(translated)
        content = (tmp_path / f"{result.slug}.md").read_text(encoding="utf-8")
        assert "---" in content
        assert "Переведённый заголовок" in content
        assert "source: https://example.com/article" in content

    @pytest.mark.asyncio
    async def test_file_contains_translated_content(self, tmp_path, translated):
        dest = MarkdownDestination(output_dir=str(tmp_path))
        result = await dest.publish(translated)
        content = (tmp_path / f"{result.slug}.md").read_text(encoding="utf-8")
        assert "Русский контент для статьи" in content

    @pytest.mark.asyncio
    async def test_slug_generation(self, tmp_path, translated):
        dest = MarkdownDestination(output_dir=str(tmp_path))
        result = await dest.publish(translated)
        assert result.slug != ""
        # Slug should be lowercase, no special chars
        assert result.slug == result.slug.lower()
        assert " " not in result.slug

    @pytest.mark.asyncio
    async def test_creates_output_dir(self, tmp_path, translated):
        new_dir = tmp_path / "nested" / "output"
        dest = MarkdownDestination(output_dir=str(new_dir))
        result = await dest.publish(translated)
        assert result.success is True
        assert new_dir.exists()

    @pytest.mark.asyncio
    async def test_tags_in_frontmatter(self, tmp_path, translated):
        dest = MarkdownDestination(output_dir=str(tmp_path))
        result = await dest.publish(translated)
        content = (tmp_path / f"{result.slug}.md").read_text(encoding="utf-8")
        assert "python" in content
        assert "testing" in content
