"""Telegram destination — send articles to a Telegram channel/chat via Bot API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from pipepost.destinations.base import Destination
from pipepost.exceptions import PublishError


if TYPE_CHECKING:
    from pipepost.core.context import PublishResult, TranslatedArticle

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot"


def _format_tags(tags: list[str]) -> str:
    """Format tags as Telegram hashtags."""
    return " ".join(f"#{tag.replace(' ', '_').replace('-', '_')}" for tag in tags if tag)


def _build_message(article: TranslatedArticle) -> str:
    """Build a formatted Telegram message from a translated article."""
    parts: list[str] = []

    parts.append(f"<b>{article.title_translated}</b>")
    parts.append("")

    content = article.content_translated[:500]
    if len(article.content_translated) > 500:
        content += "..."
    parts.append(content)
    parts.append("")

    if article.tags:
        parts.append(_format_tags(article.tags))
        parts.append("")

    parts.append(f'<a href="{article.source_url}">Source</a>')

    return "\n".join(parts)


class TelegramDestination(Destination):
    """Send translated articles to a Telegram channel or chat."""

    name = "telegram"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        parse_mode: str = "HTML",
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.parse_mode = parse_mode

    async def publish(self, article: TranslatedArticle) -> PublishResult:
        """Publish article to Telegram via Bot API."""
        from pipepost.core.context import PublishResult

        text = _build_message(article)
        url_base = f"{_API_BASE}{self.bot_token}"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if article.cover_image:
                    resp = await client.post(
                        f"{url_base}/sendPhoto",
                        json={
                            "chat_id": self.chat_id,
                            "photo": article.cover_image,
                            "caption": text,
                            "parse_mode": self.parse_mode,
                        },
                    )
                else:
                    resp = await client.post(
                        f"{url_base}/sendMessage",
                        json={
                            "chat_id": self.chat_id,
                            "text": text,
                            "parse_mode": self.parse_mode,
                        },
                    )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise PublishError(
                f"Telegram API returned {exc.response.status_code}: {exc.response.text[:200]}",
            ) from exc
        except httpx.RequestError as exc:
            raise PublishError(f"Telegram request failed: {exc}") from exc

        result_data = data.get("result", {})
        message_id = str(result_data.get("message_id", ""))

        # Build public URL for public channels (chat_id starts with @)
        url = ""
        if self.chat_id.startswith("@") and message_id:
            channel = self.chat_id.lstrip("@")
            url = f"https://t.me/{channel}/{message_id}"

        return PublishResult(success=True, slug=message_id, url=url)

    @classmethod
    def from_config(cls, config: dict[str, object]) -> TelegramDestination:
        """Create from YAML config."""
        return cls(
            bot_token=str(config["bot_token"]),
            chat_id=str(config["chat_id"]),
            parse_mode=str(config.get("parse_mode", "HTML")),
        )
