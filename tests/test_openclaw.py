"""Tests for OpenClawDestination."""

from __future__ import annotations

import json

import pytest
import respx

from pipepost.core.context import TranslatedArticle
from pipepost.destinations.openclaw import OpenClawDestination, _ws_to_http
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
def dest():
    return OpenClawDestination(
        gateway_url="ws://127.0.0.1:18789",
        session_id="sess-123",
    )


@pytest.fixture
def dest_with_channels():
    return OpenClawDestination(
        gateway_url="ws://127.0.0.1:18789",
        session_id="sess-123",
        channels=["telegram", "slack", "discord"],
    )


class TestOpenClawPublish:
    @pytest.mark.asyncio
    @respx.mock
    async def test_publish_sends_correct_payload(self, translated, dest):
        route = respx.post("http://127.0.0.1:18789/api/sessions/send").respond(
            json={"message_id": "msg-42"},
        )

        result = await dest.publish(translated)

        assert result.success is True
        assert result.slug == "msg-42"
        body = json.loads(route.calls[0].request.content)
        assert body["type"] == "message"
        assert body["action"] == "sessions_send"
        assert body["target_session"] == "sess-123"
        assert body["content"]["title"] == "Translated Title"
        assert body["content"]["source_url"] == "https://example.com/article"
        assert body["content"]["tags"] == ["python", "async"]
        assert body["content"]["cover_image"] == "https://example.com/cover.jpg"

    @pytest.mark.asyncio
    @respx.mock
    async def test_publish_with_channels(self, translated, dest_with_channels):
        route = respx.post("http://127.0.0.1:18789/api/sessions/send").respond(
            json={"message_id": "msg-99"},
        )

        result = await dest_with_channels.publish(translated)

        assert result.success is True
        body = json.loads(route.calls[0].request.content)
        assert body["content"]["channels"] == ["telegram", "slack", "discord"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_publish_no_channels(self, translated, dest):
        route = respx.post("http://127.0.0.1:18789/api/sessions/send").respond(
            json={"message_id": "msg-1"},
        )

        await dest.publish(translated)

        body = json.loads(route.calls[0].request.content)
        assert body["content"]["channels"] == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_server_error_raises_publish_error(self, translated, dest):
        respx.post("http://127.0.0.1:18789/api/sessions/send").respond(status_code=500)

        with pytest.raises(PublishError, match="500"):
            await dest.publish(translated)

    def test_from_config(self):
        config: dict[str, object] = {
            "gateway_url": "ws://10.0.0.1:9999",
            "session_id": "my-session",
            "channels": ["telegram", "slack"],
        }
        dest = OpenClawDestination.from_config(config)
        assert dest.gateway_url == "ws://10.0.0.1:9999"
        assert dest.session_id == "my-session"
        assert dest.channels == ["telegram", "slack"]

    def test_from_config_defaults(self):
        config: dict[str, object] = {}
        dest = OpenClawDestination.from_config(config)
        assert dest.gateway_url == "ws://127.0.0.1:18789"
        assert dest.session_id == ""
        assert dest.channels == []

    def test_gateway_url_conversion(self):
        assert _ws_to_http("ws://localhost:8080") == "http://localhost:8080"
        assert _ws_to_http("wss://example.com") == "https://example.com"
        assert _ws_to_http("http://already.http") == "http://already.http"

    @pytest.mark.asyncio
    @respx.mock
    async def test_content_truncated(self, dest):
        long_content = "A" * 5000
        article = TranslatedArticle(
            title="T",
            title_translated="TT",
            content="C",
            content_translated=long_content,
            source_url="https://x.com",
            tags=[],
        )

        route = respx.post("http://127.0.0.1:18789/api/sessions/send").respond(
            json={"message_id": "msg-trunc"},
        )

        await dest.publish(article)

        body = json.loads(route.calls[0].request.content)
        assert len(body["content"]["body"]) == 2000
