"""Webhook destination — POST article to any URL."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from pipepost.destinations.base import Destination
from pipepost.exceptions import PublishError


if TYPE_CHECKING:
    from pipepost.core.context import PublishResult, TranslatedArticle

logger = logging.getLogger(__name__)


class WebhookDestination(Destination):
    """POST translated article to a webhook URL."""

    name = "webhook"

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}

    async def publish(self, article: TranslatedArticle) -> PublishResult:
        """Send article as JSON to the webhook URL."""
        from pipepost.core.context import PublishResult

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

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(self.url, json=payload, headers=self.headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise PublishError(
                f"Webhook returned {exc.response.status_code}: {exc.response.text[:200]}",
            ) from exc
        except httpx.RequestError as exc:
            raise PublishError(f"Webhook request failed: {exc}") from exc

        return PublishResult(
            success=True,
            slug=data.get("slug", ""),
            url=data.get("url", ""),
        )

    @classmethod
    def from_config(cls, config: dict[str, object]) -> WebhookDestination:
        """Create from YAML config."""
        return cls(
            url=str(config["url"]),
            headers=config.get("headers"),  # type: ignore[arg-type]
        )
