"""Download images from article content and rewrite URLs to local paths."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from pipepost.core.registry import register_step
from pipepost.core.step import Step


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext

logger = logging.getLogger(__name__)

_USER_AGENT = "PipePost/1.0 (+https://github.com/DenSul/pipepost)"

_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

_CONTENT_TYPE_MAP: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}

_SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"})


def _extension_from_content_type(content_type: str) -> str | None:
    """Extract file extension from Content-Type header value."""
    base = content_type.split(";")[0].strip().lower()
    return _CONTENT_TYPE_MAP.get(base)


def _extension_from_url(url: str) -> str | None:
    """Extract file extension from URL path."""
    path = url.split("?")[0].split("#")[0]
    dot = path.rfind(".")
    if dot == -1:
        return None
    ext = path[dot:].lower()
    return ext if ext in _SUPPORTED_EXTENSIONS else None


class ImageStep(Step):
    """Download images referenced in translated content and rewrite URLs to local paths."""

    name = "images"

    def __init__(
        self,
        output_dir: str = "./output/images",
        timeout: float = 15.0,
        max_images: int = 20,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.timeout = timeout
        self.max_images = max_images

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if there is no translated article."""
        return ctx.translated is None

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Download images and rewrite URLs in translated content."""
        from pipepost.core.context import TranslatedArticle

        if ctx.translated is None:
            return ctx

        self.output_dir.mkdir(parents=True, exist_ok=True)

        content = ctx.translated.content_translated
        image_urls = self._extract_image_urls(content)

        # Collect all URLs to download (content images + cover)
        urls_to_download: list[str] = [url for _, url in image_urls[: self.max_images]]

        cover_image = ctx.translated.cover_image
        include_cover = (
            cover_image is not None
            and cover_image not in urls_to_download
            and len(urls_to_download) < self.max_images
        )
        if include_cover and cover_image is not None:
            urls_to_download.append(cover_image)

        # Download all images
        url_map: dict[str, str] = {}
        failed = 0
        for url in urls_to_download:
            local_filename = await self._download_image(url, self.output_dir)
            if local_filename is not None:
                url_map[url] = f"images/{local_filename}"
            else:
                failed += 1

        downloaded = len(url_map)
        total = downloaded + failed
        if total > 0:
            logger.info(
                "Downloaded %d/%d images (%d failed)",
                downloaded,
                total,
                failed,
            )

        # Rewrite content
        new_content = self._rewrite_content(content, url_map)

        # Rewrite cover image
        new_cover = ctx.translated.cover_image
        if new_cover is not None and new_cover in url_map:
            new_cover = url_map[new_cover]

        # Create updated TranslatedArticle (dataclass — replace fields)
        ctx.translated = TranslatedArticle(
            title=ctx.translated.title,
            title_translated=ctx.translated.title_translated,
            content=ctx.translated.content,
            content_translated=new_content,
            source_url=ctx.translated.source_url,
            source_name=ctx.translated.source_name,
            tags=list(ctx.translated.tags),
            cover_image=new_cover,
            metadata=dict(ctx.translated.metadata),
        )

        return ctx

    def _extract_image_urls(self, text: str) -> list[tuple[str, str]]:
        """Return list of (alt_text, url) from markdown image syntax."""
        return _IMAGE_PATTERN.findall(text)

    async def _download_image(self, url: str, output_dir: Path) -> str | None:
        """Download one image, return local filename or None on failure."""
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
                resp.raise_for_status()

            # Determine extension
            content_type = resp.headers.get("content-type", "")
            ext = _extension_from_content_type(content_type) or _extension_from_url(url) or ".jpg"

            # Deterministic filename from URL hash
            url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
            filename = f"{url_hash}{ext}"

            filepath = output_dir / filename
            filepath.write_bytes(resp.content)
            return filename

        except (httpx.HTTPError, OSError) as exc:
            logger.warning("Failed to download image %s: %s", url, exc)
            return None

    def _rewrite_content(self, content: str, url_map: dict[str, str]) -> str:
        """Replace original URLs with local paths in markdown content."""
        result = content
        for original_url, local_path in url_map.items():
            result = result.replace(original_url, local_path)
        return result


register_step("images", ImageStep)
