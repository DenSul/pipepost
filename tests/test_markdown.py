"""Tests for MarkdownDestination — real file writes to tmpdir."""

from __future__ import annotations

import datetime
import re

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
        assert "https://example.com/article" in content

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


class TestSlugDatePrefix:
    def test_slug_has_date_prefix(self):
        slug = MarkdownDestination._slugify("Hello World")
        today = datetime.date.today().isoformat()  # noqa: DTZ011
        assert slug.startswith(today), f"Slug {slug!r} should start with {today}"

    def test_slug_date_format(self):
        slug = MarkdownDestination._slugify("Test Article")
        # Should match YYYY-MM-DD-<text>
        assert re.match(r"^\d{4}-\d{2}-\d{2}-.+", slug)


class TestSlugDedupCounter:
    @pytest.mark.asyncio
    async def test_slug_dedup_counter(self, tmp_path, translated):
        """Two articles with same title get different slugs."""
        dest = MarkdownDestination(output_dir=str(tmp_path))
        result1 = await dest.publish(translated)
        result2 = await dest.publish(translated)

        assert result1.success is True
        assert result2.success is True
        assert result1.slug != result2.slug
        assert result2.slug.endswith("-2")
        assert (tmp_path / f"{result1.slug}.md").exists()
        assert (tmp_path / f"{result2.slug}.md").exists()

    @pytest.mark.asyncio
    async def test_slug_dedup_triple(self, tmp_path, translated):
        """Three publishes of the same title produce -2, -3 suffixes."""
        dest = MarkdownDestination(output_dir=str(tmp_path))
        r1 = await dest.publish(translated)
        r2 = await dest.publish(translated)
        r3 = await dest.publish(translated)
        assert r1.slug != r2.slug != r3.slug
        assert r3.slug.endswith("-3")


class TestSlugTransliteration:
    def test_slug_transliteration(self):
        """Cyrillic to Latin still works."""
        slug = MarkdownDestination._slugify("Привет мир")
        assert "privet" in slug
        assert "mir" in slug
        # Should not contain Cyrillic characters
        assert not re.search(r"[а-яА-ЯёЁ]", slug)

    def test_slug_max_length(self):
        """Slug text portion is truncated to 60 chars."""
        long_title = "a" * 200
        slug = MarkdownDestination._slugify(long_title)
        # date prefix is 10 chars + dash = 11, text portion max 60
        assert len(slug) <= 71
