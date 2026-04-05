"""Interactive Telegram bot for content curation."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

import httpx

from pipepost.core.registry import get_source
from pipepost.exceptions import PipePostError


if TYPE_CHECKING:
    from pipepost.core.context import Candidate

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot"


class CuratorBot:
    """Long-polling Telegram bot for interactive content curation."""

    def __init__(
        self,
        bot_token: str,
        flow_name: str = "default",
        source_name: str = "",
        target_lang: str = "ru",
    ) -> None:
        self.bot_token = bot_token
        self.flow_name = flow_name
        self.source_name = source_name
        self.target_lang = target_lang
        self._pending: dict[str, Candidate] = {}
        self._offset: int = 0
        self._url_base = f"{_API_BASE}{bot_token}"

    async def start(self) -> None:
        """Main loop — long-poll for updates and dispatch handlers."""
        logger.info("CuratorBot starting (source=%s, lang=%s)", self.source_name, self.target_lang)
        async with httpx.AsyncClient(timeout=60) as client:
            self._client = client
            while True:
                try:
                    updates = await self._get_updates()
                    for update in updates:
                        await self._dispatch(update)
                except httpx.RequestError as exc:
                    logger.warning("Polling error: %s", exc)
                    await asyncio.sleep(5)
                except Exception as exc:
                    logger.error("Unexpected error in bot loop: %s", exc)
                    await asyncio.sleep(5)

    async def _get_updates(self) -> list[dict[str, object]]:
        """Long-poll Telegram getUpdates."""
        resp = await self._client.get(
            f"{self._url_base}/getUpdates",
            params={"offset": self._offset, "timeout": 30},
        )
        resp.raise_for_status()
        data = resp.json()
        results: list[dict[str, object]] = data.get("result", [])
        if results:
            self._offset = int(str(results[-1]["update_id"])) + 1
        return results

    async def _dispatch(self, update: dict[str, object]) -> None:
        """Route an update to the appropriate handler."""
        if "message" in update:
            message = update["message"]
            if isinstance(message, dict):
                text = str(message.get("text", ""))
                chat = message.get("chat", {})
                if isinstance(chat, dict):
                    chat_id = int(str(chat.get("id", 0)))
                    if text.startswith("/scout"):
                        await self._handle_scout(chat_id)

        if "callback_query" in update:
            callback = update["callback_query"]
            if isinstance(callback, dict):
                await self._handle_callback(callback)

    async def _handle_scout(self, chat_id: int) -> None:
        """Fetch candidates and send them as messages with inline keyboards."""
        if not self.source_name:
            await self._send_message(chat_id, "No source configured. Use --source flag.")
            return

        try:
            source = get_source(self.source_name)
            candidates = await source.fetch_candidates(limit=5)
        except Exception as exc:
            await self._send_message(chat_id, f"Scout error: {exc}")
            return

        if not candidates:
            await self._send_message(chat_id, "No candidates found.")
            return

        for candidate in candidates:
            key = str(uuid.uuid4())[:8]
            self._pending[key] = candidate

            text = (
                f"\U0001f4f0 {candidate.title}\n"
                f"\U0001f517 {candidate.url}\n"
                f"\U0001f4ca Score: {candidate.score}"
            )

            reply_markup: dict[str, object] = {
                "inline_keyboard": [
                    [
                        {"text": "\u2705 Publish", "callback_data": f"publish:{key}"},
                        {"text": "\u23ed Skip", "callback_data": f"skip:{key}"},
                    ],
                ],
            }

            await self._send_message(chat_id, text, reply_markup=reply_markup)

    async def _handle_callback(self, callback_query: dict[str, object]) -> None:
        """Handle publish/skip callback from inline keyboard."""
        callback_id = str(callback_query.get("id", ""))
        data = str(callback_query.get("data", ""))
        message = callback_query.get("message", {})

        chat_id = 0
        message_id = 0
        if isinstance(message, dict):
            chat = message.get("chat", {})
            if isinstance(chat, dict):
                chat_id = int(str(chat.get("id", 0)))
            message_id = int(str(message.get("message_id", 0)))

        await self._answer_callback(callback_id)

        if ":" not in data:
            return
        action, key = data.split(":", 1)

        if action == "skip":
            await self._edit_message(chat_id, message_id, "Skipped.")
            self._pending.pop(key, None)
            return

        if action == "publish":
            candidate = self._pending.pop(key, None)
            if not candidate:
                await self._edit_message(chat_id, message_id, "Candidate expired.")
                return
            await self._run_pipeline(chat_id, message_id, candidate)

    async def _run_pipeline(
        self,
        chat_id: int,
        message_id: int,
        candidate: Candidate,
    ) -> None:
        """Run the full pipeline for a single candidate."""
        from pipepost.core.context import FlowContext
        from pipepost.core.registry import get_flow

        await self._edit_message(chat_id, message_id, f"Publishing: {candidate.title}...")

        ctx = FlowContext(
            source_name=self.source_name,
            target_lang=self.target_lang,
            candidates=[candidate],
        )

        try:
            flow = get_flow(self.flow_name)
            result = await flow.run(ctx)
        except (KeyError, PipePostError) as exc:
            await self._edit_message(chat_id, message_id, f"Error: {exc}")
            return

        if result.published and result.published.success:
            await self._edit_message(
                chat_id,
                message_id,
                f"Published: {result.published.slug}",
            )
        elif result.errors:
            await self._edit_message(
                chat_id,
                message_id,
                f"Error: {'; '.join(result.errors)}",
            )
        else:
            await self._edit_message(chat_id, message_id, "No result.")

    async def _send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Send a message via Telegram Bot API."""
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        resp = await self._client.post(f"{self._url_base}/sendMessage", json=payload)
        resp.raise_for_status()
        data: dict[str, object] = resp.json()
        return data

    async def _answer_callback(self, callback_query_id: str) -> None:
        """Acknowledge a callback query."""
        await self._client.post(
            f"{self._url_base}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id},
        )

    async def _edit_message(self, chat_id: int, message_id: int, text: str) -> None:
        """Edit an existing message."""
        await self._client.post(
            f"{self._url_base}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
            },
        )
