"""Tests for CuratorBot."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from pipepost.bot.curator import CuratorBot, _build_bot_flow
from pipepost.core.context import Candidate, FlowContext, PublishResult


@pytest.fixture
def bot():
    return CuratorBot(
        bot_token="123:ABC",
        source_name="test_source",
        target_lang="ru",
    )


def _make_candidate(title="Test Article", url="https://example.com/1", score=0.9):
    return Candidate(title=title, url=url, score=score, source_name="test_source")


class TestHandleScout:
    @pytest.mark.asyncio
    @respx.mock
    async def test_handle_scout_sends_candidates(self, bot):
        candidates = [_make_candidate(), _make_candidate(title="Second", url="https://x.com/2")]
        mock_source = MagicMock()
        mock_source.fetch_candidates = AsyncMock(return_value=candidates)

        route = respx.post("https://api.telegram.org/bot123:ABC/sendMessage").respond(
            json={"ok": True, "result": {"message_id": 1}},
        )

        async with httpx.AsyncClient(timeout=60) as client:
            bot._client = client
            with patch("pipepost.bot.curator.get_source", return_value=mock_source):
                await bot._handle_scout(chat_id=111)

        assert route.call_count == 2
        # Verify inline keyboard is present in the requests
        import json

        for call in route.calls:
            body = json.loads(call.request.content)
            assert "reply_markup" in body
            assert "inline_keyboard" in body["reply_markup"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_handle_scout_no_source(self):
        bot = CuratorBot(bot_token="123:ABC", source_name="", target_lang="ru")
        route = respx.post("https://api.telegram.org/bot123:ABC/sendMessage").respond(
            json={"ok": True, "result": {"message_id": 1}},
        )

        async with httpx.AsyncClient(timeout=60) as client:
            bot._client = client
            await bot._handle_scout(chat_id=111)

        assert route.call_count == 1
        import json

        body = json.loads(route.calls[0].request.content)
        assert "No source configured" in body["text"]


class TestHandleCallback:
    @pytest.mark.asyncio
    @respx.mock
    async def test_handle_publish_callback(self, bot):
        candidate = _make_candidate()
        bot._pending["abc123"] = candidate

        respx.post("https://api.telegram.org/bot123:ABC/answerCallbackQuery").respond(
            json={"ok": True},
        )
        edit_route = respx.post("https://api.telegram.org/bot123:ABC/editMessageText").respond(
            json={"ok": True},
        )

        mock_flow = MagicMock()
        result_ctx = FlowContext()
        result_ctx.published = PublishResult(success=True, slug="published-123")
        mock_flow.run = AsyncMock(return_value=result_ctx)
        bot._flow = mock_flow

        callback = {
            "id": "cb1",
            "data": "publish:abc123",
            "message": {"message_id": 10, "chat": {"id": 111}},
        }

        async with httpx.AsyncClient(timeout=60) as client:
            bot._client = client
            await bot._handle_callback(callback)

        # Should have been edited twice: once for "Publishing..." and once for result
        assert edit_route.call_count == 2
        import json

        last_body = json.loads(edit_route.calls[-1].request.content)
        assert "published-123" in last_body["text"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_handle_skip_callback(self, bot):
        candidate = _make_candidate()
        bot._pending["xyz789"] = candidate

        respx.post("https://api.telegram.org/bot123:ABC/answerCallbackQuery").respond(
            json={"ok": True},
        )
        edit_route = respx.post("https://api.telegram.org/bot123:ABC/editMessageText").respond(
            json={"ok": True},
        )

        callback = {
            "id": "cb2",
            "data": "skip:xyz789",
            "message": {"message_id": 20, "chat": {"id": 111}},
        }

        async with httpx.AsyncClient(timeout=60) as client:
            bot._client = client
            await bot._handle_callback(callback)

        assert edit_route.call_count == 1
        import json

        body = json.loads(edit_route.calls[0].request.content)
        assert body["text"] == "Skipped."
        assert "xyz789" not in bot._pending

    @pytest.mark.asyncio
    @respx.mock
    async def test_handle_expired_candidate(self, bot):
        respx.post("https://api.telegram.org/bot123:ABC/answerCallbackQuery").respond(
            json={"ok": True},
        )
        edit_route = respx.post("https://api.telegram.org/bot123:ABC/editMessageText").respond(
            json={"ok": True},
        )

        callback = {
            "id": "cb3",
            "data": "publish:gone",
            "message": {"message_id": 30, "chat": {"id": 111}},
        }

        async with httpx.AsyncClient(timeout=60) as client:
            bot._client = client
            await bot._handle_callback(callback)

        import json

        body = json.loads(edit_route.calls[0].request.content)
        assert "expired" in body["text"].lower()


class TestBuildBotFlow:
    def test_bot_flow_has_expected_steps(self):
        flow = _build_bot_flow()
        step_names = [s.name for s in flow.steps]
        assert step_names == ["fetch", "translate", "validate", "publish"]
        assert flow.name == "bot"
