"""Fetch article content from URL and convert to markdown."""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from pipepost.core.context import Article, FlowContext
from pipepost.core.step import Step

logger = logging.getLogger(__name__)


class FetchStep(Step):
    name = "fetch"

    def __init__(self, max_chars: int = 20000):
        self.max_chars = max_chars

    async def execute(self, ctx: FlowContext) -> FlowContext:
        if not ctx.candidates:
            ctx.add_error("No candidates to fetch")
            return ctx

        for candidate in ctx.candidates[:5]:
            if candidate.url in ctx.existing_urls:
                continue
            try:
                content = await self._fetch_and_convert(candidate.url)
                if len(content) < 200:
                    logger.warning("Article too short (%d): %s", len(content), candidate.url)
                    continue
                cover = await self._extract_og_image(candidate.url)
                ctx.selected = Article(
                    url=candidate.url,
                    title=candidate.title,
                    content=content,
                    cover_image=cover,
                    metadata=candidate.metadata,
                )
                return ctx
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", candidate.url, e)

        ctx.add_error("All candidates unfetchable")
        return ctx

    async def _fetch_and_convert(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "PipePost/1.0"})
            resp.raise_for_status()
            return self._html_to_markdown(resp.text)

    async def _extract_og_image(self, url: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "PipePost/1.0"})
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                for attr in ("property", "name"):
                    tag = soup.find("meta", attrs={attr: "og:image"})
                    if tag and tag.get("content"):
                        return str(tag["content"])
                return None
        except Exception:
            return None

    def _html_to_markdown(self, html: str) -> str:
        """Simple HTML to markdown conversion."""
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        article = (
            soup.find("article")
            or soup.find("main")
            or soup.find("div", class_=re.compile(r"content|post|article", re.I))
        )
        target = article or soup.body or soup
        text = target.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[: self.max_chars]
