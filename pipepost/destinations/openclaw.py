"""OpenClaw destination — send articles through OpenClaw's HTTP Gateway."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from pipepost.destinations.base import Destination
from pipepost.exceptions import PublishError


if TYPE_CHECKING:
    from pipepost.core.context import PublishResult, TranslatedArticle

logger = logging.getLogger(__name__)

_MAX_BODY_LENGTH = 2000


def _ws_to_http(url: str) -> str:
    """Convert ws:// or wss:// URL to http:// or https://."""
    if url.startswith("wss://"):
        return "https://" + url[6:]
    if url.startswith("ws://"):
        return "http://" + url[5:]
    return url


class OpenClawDestination(Destination):
    """Send translated articles through OpenClaw's HTTP Gateway."""

    name = "openclaw"

    def __init__(
        self,
        gateway_url: str = "ws://127.0.0.1:18789",
        session_id: str = "",
        channels: list[str] | None = None,
    ) -> None:
        self.gateway_url = gateway_url
        self.session_id = session_id
        self.channels = channels or []

    async def publish(self, article: TranslatedArticle) -> PublishResult:
        """Send article to OpenClaw Gateway via HTTP POST."""
        from pipepost.core.context import PublishResult

        payload = {
            "type": "message",
            "action": "sessions_send",
            "target_session": self.session_id,
            "content": {
                "title": article.title_translated,
                "body": article.content_translated[:_MAX_BODY_LENGTH],
                "source_url": article.source_url,
                "tags": article.tags,
                "cover_image": article.cover_image,
                "channels": self.channels,
            },
        }

        http_url = _ws_to_http(self.gateway_url)
        url = f"{http_url.rstrip('/')}/api/sessions/send"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise PublishError(
                f"OpenClaw returned {exc.response.status_code}: {exc.response.text[:200]}",
            ) from exc
        except httpx.RequestError as exc:
            raise PublishError(f"OpenClaw request failed: {exc}") from exc

        message_id = str(data.get("message_id", ""))

        return PublishResult(success=True, slug=message_id)

    @classmethod
    def from_config(cls, config: dict[str, object]) -> OpenClawDestination:
        """Create from YAML config."""
        channels_raw = config.get("channels")
        channels: list[str] | None = None
        if isinstance(channels_raw, list):
            channels = [str(c) for c in channels_raw]

        return cls(
            gateway_url=str(config.get("gateway_url", "ws://127.0.0.1:18789")),
            session_id=str(config.get("session_id", "")),
            channels=channels,
        )
