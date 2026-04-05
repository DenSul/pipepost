"""Tests for ImageStep — image downloading and URL rewriting."""

from __future__ import annotations

import hashlib

import pytest
import respx

from pipepost.core.context import FlowContext, TranslatedArticle
from pipepost.steps.images import ImageStep


def _make_translated(
    content: str = "No images here.",
    cover_image: str | None = None,
) -> TranslatedArticle:
    return TranslatedArticle(
        title="Original",
        title_translated="Translated",
        content="original content",
        content_translated=content,
        source_url="https://example.com/article",
        source_name="test",
        cover_image=cover_image,
    )


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


class TestImageStepDownloads:
    @pytest.mark.asyncio
    @respx.mock
    async def test_downloads_and_rewrites_images(self, tmp_path):
        img_dir = tmp_path / "images"
        step = ImageStep(output_dir=str(img_dir))

        content = (
            "Hello\n"
            "![Logo](https://img.example.com/logo.png)\n"
            "Some text\n"
            "![Photo](https://img.example.com/photo.jpg)\n"
        )
        ctx = FlowContext(translated=_make_translated(content=content))

        respx.get("https://img.example.com/logo.png").respond(
            content=b"PNG_DATA",
            headers={"content-type": "image/png"},
        )
        respx.get("https://img.example.com/photo.jpg").respond(
            content=b"JPEG_DATA",
            headers={"content-type": "image/jpeg"},
        )

        result = await step.execute(ctx)

        assert result.translated is not None
        assert "images/" in result.translated.content_translated
        assert "https://img.example.com/logo.png" not in result.translated.content_translated
        assert "https://img.example.com/photo.jpg" not in result.translated.content_translated

        # Verify files exist
        files = list(img_dir.iterdir())
        assert len(files) == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_download_failure_gracefully(self, tmp_path):
        img_dir = tmp_path / "images"
        step = ImageStep(output_dir=str(img_dir))

        content = (
            "![Good](https://img.example.com/good.png)\n![Bad](https://img.example.com/bad.png)\n"
        )
        ctx = FlowContext(translated=_make_translated(content=content))

        respx.get("https://img.example.com/good.png").respond(
            content=b"PNG_DATA",
            headers={"content-type": "image/png"},
        )
        respx.get("https://img.example.com/bad.png").respond(status_code=404)

        result = await step.execute(ctx)

        assert result.translated is not None
        # Good image was rewritten
        assert "https://img.example.com/good.png" not in result.translated.content_translated
        # Bad image URL kept as-is
        assert "https://img.example.com/bad.png" in result.translated.content_translated

        files = list(img_dir.iterdir())
        assert len(files) == 1


class TestImageStepSkip:
    def test_skips_when_no_translated(self):
        step = ImageStep()
        ctx = FlowContext()
        assert step.should_skip(ctx) is True

    def test_does_not_skip_when_translated(self):
        step = ImageStep()
        ctx = FlowContext(translated=_make_translated())
        assert step.should_skip(ctx) is False


class TestImageStepLimits:
    @pytest.mark.asyncio
    @respx.mock
    async def test_respects_max_images(self, tmp_path):
        img_dir = tmp_path / "images"
        step = ImageStep(output_dir=str(img_dir), max_images=2)

        content = "\n".join(f"![img{i}](https://img.example.com/img{i}.png)" for i in range(5))
        ctx = FlowContext(translated=_make_translated(content=content))

        for i in range(5):
            respx.get(f"https://img.example.com/img{i}.png").respond(
                content=b"PNG_DATA",
                headers={"content-type": "image/png"},
            )

        result = await step.execute(ctx)

        assert result.translated is not None
        files = list(img_dir.iterdir())
        assert len(files) == 2


class TestImageStepCover:
    @pytest.mark.asyncio
    @respx.mock
    async def test_downloads_cover_image(self, tmp_path):
        img_dir = tmp_path / "images"
        step = ImageStep(output_dir=str(img_dir))

        cover_url = "https://img.example.com/cover.jpg"
        ctx = FlowContext(
            translated=_make_translated(content="No images.", cover_image=cover_url),
        )

        respx.get(cover_url).respond(
            content=b"COVER_DATA",
            headers={"content-type": "image/jpeg"},
        )

        result = await step.execute(ctx)

        assert result.translated is not None
        expected_hash = _url_hash(cover_url)
        assert result.translated.cover_image == f"images/{expected_hash}.jpg"

        files = list(img_dir.iterdir())
        assert len(files) == 1


class TestDeterministicFilenames:
    def test_deterministic_filenames(self):
        url = "https://img.example.com/test.png"
        hash1 = _url_hash(url)
        hash2 = _url_hash(url)
        assert hash1 == hash2
        assert len(hash1) == 16


class TestExtensionDetection:
    @pytest.mark.asyncio
    @respx.mock
    async def test_detects_extension_from_content_type(self, tmp_path):
        img_dir = tmp_path / "images"
        step = ImageStep(output_dir=str(img_dir))

        # URL has no extension, content-type is image/png
        url = "https://img.example.com/image-no-ext"
        content = f"![img]({url})\n"
        ctx = FlowContext(translated=_make_translated(content=content))

        respx.get(url).respond(
            content=b"PNG_DATA",
            headers={"content-type": "image/png"},
        )

        await step.execute(ctx)

        files = list(img_dir.iterdir())
        assert len(files) == 1
        assert files[0].suffix == ".png"

    @pytest.mark.asyncio
    @respx.mock
    async def test_detects_jpg_from_content_type(self, tmp_path):
        img_dir = tmp_path / "images"
        step = ImageStep(output_dir=str(img_dir))

        url = "https://img.example.com/photo"
        content = f"![img]({url})\n"
        ctx = FlowContext(translated=_make_translated(content=content))

        respx.get(url).respond(
            content=b"JPEG_DATA",
            headers={"content-type": "image/jpeg"},
        )

        await step.execute(ctx)

        files = list(img_dir.iterdir())
        assert len(files) == 1
        assert files[0].suffix == ".jpg"


class TestOutputDir:
    @pytest.mark.asyncio
    @respx.mock
    async def test_creates_output_dir(self, tmp_path):
        img_dir = tmp_path / "nested" / "deep" / "images"
        step = ImageStep(output_dir=str(img_dir))

        content = "![img](https://img.example.com/test.png)\n"
        ctx = FlowContext(translated=_make_translated(content=content))

        respx.get("https://img.example.com/test.png").respond(
            content=b"PNG_DATA",
            headers={"content-type": "image/png"},
        )

        await step.execute(ctx)

        assert img_dir.exists()
        assert len(list(img_dir.iterdir())) == 1


class TestExtractImageUrls:
    def test_extract_image_urls(self):
        step = ImageStep()
        text = (
            "Hello ![Alt1](https://example.com/1.png) world "
            "![Alt2](https://example.com/2.jpg)\n"
            "No image here\n"
            "![](https://example.com/3.gif)\n"
        )
        urls = step._extract_image_urls(text)
        assert len(urls) == 3
        assert urls[0] == ("Alt1", "https://example.com/1.png")
        assert urls[1] == ("Alt2", "https://example.com/2.jpg")
        assert urls[2] == ("", "https://example.com/3.gif")


class TestNoImages:
    @pytest.mark.asyncio
    async def test_no_images_in_content(self, tmp_path):
        img_dir = tmp_path / "images"
        step = ImageStep(output_dir=str(img_dir))

        content = "This is plain text with no images at all."
        ctx = FlowContext(translated=_make_translated(content=content))

        result = await step.execute(ctx)

        assert result.translated is not None
        assert result.translated.content_translated == content
        # Directory created but empty
        assert img_dir.exists()
        assert len(list(img_dir.iterdir())) == 0
