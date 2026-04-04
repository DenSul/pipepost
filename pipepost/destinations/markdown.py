"""Markdown file destination — save articles as .md files."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from pipepost.destinations.base import Destination


if TYPE_CHECKING:
    from pipepost.core.context import PublishResult, TranslatedArticle

logger = logging.getLogger(__name__)


class MarkdownDestination(Destination):
    """Save translated articles as markdown files with YAML frontmatter."""

    name = "markdown"

    def __init__(self, output_dir: str = "./output") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def publish(self, article: TranslatedArticle) -> PublishResult:
        """Write article to a .md file."""
        from pipepost.core.context import PublishResult

        slug = self._slugify(article.title_translated or article.title)
        filepath = self.output_dir / f"{slug}.md"

        frontmatter = (
            f'---\ntitle: "{article.title_translated}"\n'
            f'title_en: "{article.title}"\n'
            f"source: {article.source_url}\n"
            f"tags: {article.tags}\n---\n\n"
        )
        content = frontmatter + article.content_translated

        filepath.write_text(content, encoding="utf-8")
        logger.info("Saved to %s", filepath)

        return PublishResult(success=True, slug=slug, url=str(filepath))

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to URL-friendly slug."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_]+", "-", text)
        return text[:80].strip("-")
