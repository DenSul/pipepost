"""Tests for TelegramDestination."""

from __future__ import annotations

import json

import pytest
import respx

from pipepost.core.context import TranslatedArticle
from pipepost.destinations.telegram import TelegramDestination, _build_message, _format_tags
from pipepost.exceptions import PublishError


@pytest.fixture
def translated():
    return TranslatedArticle(
        title="Original Title",
        title_translated="Translated Title",
        content="English content",
        content_translated="Translated content goes here",
        source_url="https://example.com/article",
        source_name="test",
        tags=["python", "async"],
        cover_image="https://example.com/cover.jpg",
    )


@pytest.fixture
def translated_no_image():
    return TranslatedArticle(
        title="Original Title",
        title_translated="Translated Title",
        content="English content",
        content_translated="Translated content goes here",
        source_url="https://example.com/article",
        source_name="test",
        tags=["python", "async"],
        cover_image=None,
    )


@pytest.fixture
def dest():
    return TelegramDestination(bot_token="123:ABC", chat_id="@mychannel")


class TestTelegramPublish:
    @pytest.mark.asyncio
    @respx.mock
    async def test_sends_message_with_correct_payload(self, translated_no_image, dest):
        route = respx.post("https://api.telegram.org/bot123:ABC/sendMessage").respond(
            json={"ok": True, "result": {"message_id": 42}},
        )

        result = await dest.publish(translated_no_image)

        assert result.success is True
        assert result.slug == "42"
        body = json.loads(route.calls[0].request.content)
        assert body["chat_id"] == "@mychannel"
        assert body["parse_mode"] == "HTML"
        assert "<b>Translated Title</b>" in body["text"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_sends_photo_when_cover_image_present(self, translated, dest):
        route = respx.post("https://api.telegram.org/bot123:ABC/sendPhoto").respond(
            json={"ok": True, "result": {"message_id": 99}},
        )

        result = await dest.publish(translated)

        assert result.success is True
        assert result.slug == "99"
        body = json.loads(route.calls[0].request.content)
        assert body["photo"] == "https://example.com/cover.jpg"
        assert "<b>Translated Title</b>" in body["caption"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_sends_message_when_no_cover_image(self, translated_no_image, dest):
        route = respx.post("https://api.telegram.org/bot123:ABC/sendMessage").respond(
            json={"ok": True, "result": {"message_id": 1}},
        )

        await dest.publish(translated_no_image)

        assert route.called
        assert len(route.calls) == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_server_error_raises_publish_error(self, translated_no_image, dest):
        respx.post("https://api.telegram.org/bot123:ABC/sendMessage").respond(status_code=400)

        with pytest.raises(PublishError, match="400"):
            await dest.publish(translated_no_image)

    @pytest.mark.asyncio
    @respx.mock
    async def test_server_500_raises_publish_error(self, translated, dest):
        respx.post("https://api.telegram.org/bot123:ABC/sendPhoto").respond(status_code=500)

        with pytest.raises(PublishError, match="500"):
            await dest.publish(translated)

    def test_formats_tags_as_hashtags(self):
        result = _format_tags(["python", "async io", "type-checking"])
        assert "#python" in result
        assert "#async_io" in result
        assert "#type_checking" in result

    def test_formats_empty_tags(self):
        assert _format_tags([]) == ""

    def test_from_config(self):
        config: dict[str, object] = {
            "bot_token": "tok:123",
            "chat_id": "@chan",
            "parse_mode": "Markdown",
        }
        dest = TelegramDestination.from_config(config)
        assert dest.bot_token == "tok:123"
        assert dest.chat_id == "@chan"
        assert dest.parse_mode == "Markdown"

    def test_from_config_defaults(self):
        config: dict[str, object] = {"bot_token": "tok:123", "chat_id": "-100123"}
        dest = TelegramDestination.from_config(config)
        assert dest.parse_mode == "HTML"

    @pytest.mark.asyncio
    @respx.mock
    async def test_public_channel_url(self, translated_no_image):
        respx.post("https://api.telegram.org/bot123:ABC/sendMessage").respond(
            json={"ok": True, "result": {"message_id": 7}},
        )
        dest = TelegramDestination(bot_token="123:ABC", chat_id="@pubchan")
        result = await dest.publish(translated_no_image)
        assert result.url == "https://t.me/pubchan/7"

    @pytest.mark.asyncio
    @respx.mock
    async def test_private_chat_no_url(self, translated_no_image):
        respx.post("https://api.telegram.org/bot123:ABC/sendMessage").respond(
            json={"ok": True, "result": {"message_id": 7}},
        )
        dest = TelegramDestination(bot_token="123:ABC", chat_id="-100123")
        result = await dest.publish(translated_no_image)
        assert result.url == ""

    def test_build_message_truncates_content(self):
        article = TranslatedArticle(
            title="T",
            title_translated="TT",
            content="C",
            content_translated="A" * 600,
            source_url="https://x.com",
            tags=["tag1"],
        )
        msg = _build_message(article)
        assert "..." in msg
        # Should have 500 chars + "..."
        assert "A" * 500 in msg
