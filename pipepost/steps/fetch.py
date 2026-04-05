"""Fetch article content from URL and convert to markdown."""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import httpx
from bs4 import BeautifulSoup

from pipepost.core.registry import register_step
from pipepost.core.step import Step, StepBuildContext
from pipepost.exceptions import FetchError


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pipepost.core.context import Article, FlowContext

logger = logging.getLogger(__name__)

_USER_AGENT = "PipePost/1.0 (+https://github.com/DenSul/pipepost)"
_MAX_RETRIES = 3
_BACKOFF_FACTOR = 0.5
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_DEFAULT_MAX_CONCURRENCY = 5


def _build_retry_transport() -> httpx.AsyncHTTPTransport:
    """Build an httpx transport with exponential backoff retry."""
    return httpx.AsyncHTTPTransport(retries=_MAX_RETRIES)


class FetchStep(Step):
    """Download article, extract content as markdown, get og:image."""

    name = "fetch"

    def __init__(
        self,
        max_chars: int = 20000,
        timeout: float = 30.0,
        max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        self.max_chars = max_chars
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @classmethod
    def from_config(cls, build_ctx: StepBuildContext) -> FetchStep:
        """Create from StepBuildContext."""
        return cls(max_chars=build_ctx.max_chars, timeout=build_ctx.fetch_timeout)

    @asynccontextmanager
    async def rate_limit(self) -> AsyncIterator[None]:
        """Acquire the concurrency semaphore before making an external call."""
        async with self._semaphore:
            yield

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Fetch the first viable candidate's content."""
        if not ctx.candidates:
            ctx.add_error("No candidates to fetch")
            return ctx

        for candidate in ctx.candidates[:5]:
            if candidate.url in ctx.existing_urls:
                continue
            try:
                article = await self._fetch_article(
                    candidate.url,
                    candidate.title,
                    candidate.metadata,
                )
                if len(article.content) < 200:
                    logger.warning(
                        "Article too short (%d): %s",
                        len(article.content),
                        candidate.url,
                    )
                    continue
                ctx.selected = article
                return ctx
            except FetchError as exc:
                logger.warning("Failed to fetch %s: %s", candidate.url, exc)
            except Exception as exc:
                logger.warning("Unexpected error fetching %s: %s", candidate.url, exc)

        ctx.add_error("All candidates unfetchable")
        return ctx

    async def _fetch_article(self, url: str, title: str, metadata: dict[str, object]) -> Article:
        """Fetch URL content and convert to Article."""
        from pipepost.core.context import Article

        transport = _build_retry_transport()
        async with httpx.AsyncClient(
            transport=transport,
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            try:
                async with self.rate_limit():
                    resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
                    resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise FetchError(f"HTTP {exc.response.status_code} for {url}") from exc
            except httpx.RequestError as exc:
                raise FetchError(f"Request failed for {url}: {exc}") from exc

            content = self._html_to_markdown(resp.text)
            cover = self._extract_og_image_from_html(resp.text)

        return Article(
            url=url,
            title=title,
            content=content,
            cover_image=cover,
            metadata=dict(metadata),
        )

    def _extract_og_image_from_html(self, html: str) -> str | None:
        """Extract og:image from already-fetched HTML."""
        soup = BeautifulSoup(html, "html.parser")
        for attr in ("property", "name"):
            tag = soup.find("meta", attrs={attr: "og:image"})
            if tag and hasattr(tag, "get") and tag.get("content"):
                return str(tag.get("content"))
        return None

    def _html_to_markdown(self, html: str) -> str:
        """Convert HTML to markdown preserving code blocks, images, and links."""
        from markdownify import markdownify as md

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        article = (
            soup.find("article")
            or soup.find("main")
            or soup.find("div", class_=re.compile(r"content|post|article", re.I))
        )
        target = article or soup.body or soup
        text = md(str(target), heading_style="ATX", code_language="python")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[: self.max_chars]


register_step("fetch", FetchStep)
