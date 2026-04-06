"""Tests for WebhookDestination — mock httpx POST."""

from __future__ import annotations

import pytest
import respx

from pipepost.core.context import TranslatedArticle
from pipepost.destinations.webhook import WebhookDestination
from pipepost.exceptions import PublishError


@pytest.fixture
def translated():
    return TranslatedArticle(
        title="Original Title",
        title_translated="Переведённый заголовок",
        content="English content",
        content_translated="Русский контент",
        source_url="https://example.com/article",
        source_name="hackernews",
        tags=["python", "testing"],
        cover_image="https://example.com/cover.jpg",
    )


class TestWebhookPublish:
    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_publish(self, translated):
        respx.post("https://api.example.com/import").respond(
            json={"slug": "my-article", "url": "https://blog.example.com/my-article"},
        )

        dest = WebhookDestination(url="https://api.example.com/import")
        result = await dest.publish(translated)

        assert result.success is True
        assert result.slug == "my-article"
        assert result.url == "https://blog.example.com/my-article"

    @pytest.mark.asyncio
    @respx.mock
    async def test_sends_correct_payload(self, translated):
        route = respx.post("https://api.example.com/import").respond(
            json={"slug": "s", "url": "u"},
        )

        dest = WebhookDestination(url="https://api.example.com/import")
        await dest.publish(translated)

        request = route.calls[0].request
        import json

        body = json.loads(request.content)
        assert body["title"] == "Original Title"
        assert body["titleRu"] == "Переведённый заголовок"
        assert body["tags"] == ["python", "testing"]
        assert body["coverImage"] == "https://example.com/cover.jpg"

    @pytest.mark.asyncio
    @respx.mock
    async def test_server_error_raises(self, translated):
        respx.post("https://api.example.com/import").respond(status_code=500)

        dest = WebhookDestination(url="https://api.example.com/import")
        with pytest.raises(PublishError):
            await dest.publish(translated)

    @pytest.mark.asyncio
    @respx.mock
    async def test_custom_headers_sent(self, translated):
        route = respx.post("https://api.example.com/import").respond(
            json={"slug": "s", "url": "u"},
        )

        dest = WebhookDestination(
            url="https://api.example.com/import",
            headers={"Authorization": "Bearer token123", "Content-Type": "application/json"},
        )
        await dest.publish(translated)

        request = route.calls[0].request
        assert request.headers["Authorization"] == "Bearer token123"

    @pytest.mark.asyncio
    @respx.mock
    async def test_server_error_raises_publish_error(self, translated):
        from pipepost.exceptions import PublishError

        respx.post("https://api.example.com/import").respond(status_code=500)
        dest = WebhookDestination(url="https://api.example.com/import")
        with pytest.raises(PublishError, match="500"):
            await dest.publish(translated)

    @pytest.mark.asyncio
    @respx.mock
    async def test_missing_slug_in_response(self, translated):
        respx.post("https://api.example.com/import").respond(json={})
        dest = WebhookDestination(url="https://api.example.com/import")
        result = await dest.publish(translated)
        assert result.success is True
        assert result.slug == ""
        assert result.url == ""

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_cover_image_sends_null(self):
        route = respx.post("https://api.example.com/import").respond(
            json={"slug": "s", "url": "u"},
        )
        article = TranslatedArticle(
            title="T",
            title_translated="Т",
            content="C",
            content_translated="К",
            source_url="https://x.com",
            cover_image=None,
        )
        dest = WebhookDestination(url="https://api.example.com/import")
        await dest.publish(article)
        import json

        body = json.loads(route.calls[0].request.content)
        assert body["coverImage"] is None

    def test_default_headers(self):
        dest = WebhookDestination(url="https://x.com")
        assert dest.headers == {"Content-Type": "application/json"}

    def test_from_config(self):
        dest = WebhookDestination.from_config(
            {"url": "https://x.com/api", "headers": {"X-Key": "abc"}},
        )
        assert dest.url == "https://x.com/api"
        assert dest.headers["X-Key"] == "abc"

    def test_from_config_no_headers(self):
        dest = WebhookDestination.from_config({"url": "https://x.com/api"})
        assert dest.url == "https://x.com/api"
