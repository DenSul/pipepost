"""Webhook destination — POST article to any URL."""
from __future__ import annotations

import logging

import httpx

from pipepost.core.context import PublishResult, TranslatedArticle
from pipepost.destinations.base import Destination

logger = logging.getLogger(__name__)


class WebhookDestination(Destination):
    """POST translated article as JSON to a webhook URL."""

    name = "webhook"

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}

    async def publish(self, article: TranslatedArticle) -> PublishResult:
        payload = {
            "title": article.title,
            "titleRu": article.title_translated,
            "content": article.content,
            "contentRu": article.content_translated,
            "sourceUrl": article.source_url,
            "sourceName": article.source_name,
            "tags": article.tags,
            "coverImage": article.cover_image,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.url, json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()

        return PublishResult(
            success=True,
            slug=data.get("slug", ""),
            url=data.get("url", ""),
        )

    @classmethod
    def from_config(cls, config: dict[str, str]) -> WebhookDestination:
        """Create from a config dict."""
        return cls(url=config["url"], headers=config.get("headers"))
