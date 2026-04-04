"""Tests for content sources — HN, Reddit, RSS, Search."""

from __future__ import annotations

import pytest
import httpx
import respx

from pipepost.sources.hackernews import HackerNewsSource
from pipepost.sources.reddit import RedditSource
from pipepost.sources.rss import RSSSource


# ── HackerNews ──────────────────────────────────────────────────────


class TestHackerNewsSource:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_returns_candidates(self):
        respx.get("https://hacker-news.firebaseio.com/v0/topstories.json").respond(
            json=[1, 2, 3],
        )
        for sid in [1, 2, 3]:
            respx.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json").respond(
                json={
                    "id": sid,
                    "type": "story",
                    "title": f"Story {sid}",
                    "url": f"https://example.com/{sid}",
                    "score": 200 + sid,
                    "descendants": 50,
                },
            )

        src = HackerNewsSource(min_score=50)
        candidates = await src.fetch_candidates(limit=3)
        assert len(candidates) == 3
        assert candidates[0].score > candidates[1].score  # sorted desc

    @pytest.mark.asyncio
    @respx.mock
    async def test_min_score_filtering(self):
        respx.get("https://hacker-news.firebaseio.com/v0/topstories.json").respond(
            json=[10, 20],
        )
        respx.get("https://hacker-news.firebaseio.com/v0/item/10.json").respond(
            json={"id": 10, "type": "story", "title": "Low", "url": "https://a.com", "score": 5},
        )
        respx.get("https://hacker-news.firebaseio.com/v0/item/20.json").respond(
            json={"id": 20, "type": "story", "title": "High", "url": "https://b.com", "score": 500},
        )

        src = HackerNewsSource(min_score=100)
        candidates = await src.fetch_candidates(limit=10)
        assert len(candidates) == 1
        assert candidates[0].title == "High"

    @pytest.mark.asyncio
    @respx.mock
    async def test_skips_items_without_url(self):
        respx.get("https://hacker-news.firebaseio.com/v0/topstories.json").respond(json=[1])
        respx.get("https://hacker-news.firebaseio.com/v0/item/1.json").respond(
            json={"id": 1, "type": "story", "title": "Ask HN", "score": 999},
        )

        src = HackerNewsSource(min_score=0)
        candidates = await src.fetch_candidates(limit=5)
        assert len(candidates) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_skips_non_story_types(self):
        respx.get("https://hacker-news.firebaseio.com/v0/topstories.json").respond(json=[1])
        respx.get("https://hacker-news.firebaseio.com/v0/item/1.json").respond(
            json={"id": 1, "type": "job", "title": "Hiring", "url": "https://x.com", "score": 999},
        )

        src = HackerNewsSource(min_score=0)
        candidates = await src.fetch_candidates(limit=5)
        assert len(candidates) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_item_fetch_error(self):
        respx.get("https://hacker-news.firebaseio.com/v0/topstories.json").respond(json=[1, 2])
        respx.get("https://hacker-news.firebaseio.com/v0/item/1.json").respond(status_code=500)
        respx.get("https://hacker-news.firebaseio.com/v0/item/2.json").respond(
            json={"id": 2, "type": "story", "title": "OK", "url": "https://ok.com", "score": 100},
        )

        src = HackerNewsSource(min_score=0)
        candidates = await src.fetch_candidates(limit=5)
        assert len(candidates) == 1
        assert candidates[0].title == "OK"

    def test_from_config(self):
        src = HackerNewsSource.from_config({"min_score": 200})
        assert src.min_score == 200


# ── Reddit ──────────────────────────────────────────────────────────


class TestRedditSource:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_returns_candidates(self):
        respx.get(url__startswith="https://www.reddit.com/r/python").respond(
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "id": "abc",
                                "title": "Cool lib",
                                "url": "https://cool-lib.dev",
                                "score": 500,
                                "selftext": "Check this out",
                            },
                        },
                    ],
                },
            },
        )

        src = RedditSource(subreddits=["python"], min_score=100)
        candidates = await src.fetch_candidates(limit=5)
        assert len(candidates) == 1
        assert candidates[0].source_name == "reddit"

    @pytest.mark.asyncio
    @respx.mock
    async def test_min_score_filtering(self):
        respx.get(url__startswith="https://www.reddit.com/r/").respond(
            json={
                "data": {
                    "children": [
                        {"data": {"id": "1", "title": "Low", "url": "https://a.com", "score": 10}},
                        {"data": {"id": "2", "title": "High", "url": "https://b.com", "score": 999}},
                    ],
                },
            },
        )

        src = RedditSource(subreddits=["test"], min_score=100)
        candidates = await src.fetch_candidates(limit=10)
        assert len(candidates) == 1
        assert candidates[0].title == "High"

    @pytest.mark.asyncio
    @respx.mock
    async def test_skips_reddit_self_links(self):
        respx.get(url__startswith="https://www.reddit.com/r/").respond(
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "id": "x",
                                "title": "Self",
                                "url": "https://www.reddit.com/r/python/comments/...",
                                "score": 500,
                            },
                        },
                    ],
                },
            },
        )

        src = RedditSource(subreddits=["python"], min_score=0)
        candidates = await src.fetch_candidates(limit=5)
        assert len(candidates) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_subreddit_error(self):
        respx.get(url__startswith="https://www.reddit.com/r/deadzone").respond(status_code=403)
        respx.get(url__startswith="https://www.reddit.com/r/python").respond(
            json={
                "data": {
                    "children": [
                        {"data": {"id": "1", "title": "OK", "url": "https://x.com", "score": 500}},
                    ],
                },
            },
        )

        src = RedditSource(subreddits=["deadzone", "python"], min_score=0)
        candidates = await src.fetch_candidates(limit=5)
        assert len(candidates) == 1

    def test_from_config(self):
        src = RedditSource.from_config({"subreddits": ["rust"], "min_score": 50})
        assert src.subreddits == ["rust"]
        assert src.min_score == 50


# ── RSS ─────────────────────────────────────────────────────────────


RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Article One</title>
      <link>https://example.com/1</link>
      <description>First article desc</description>
    </item>
    <item>
      <title>Article Two</title>
      <link>https://example.com/2</link>
      <description>Second article desc</description>
    </item>
  </channel>
</rss>"""

ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Feed</title>
  <entry>
    <title>Atom Entry</title>
    <link rel="alternate" href="https://example.com/atom/1"/>
    <summary>Atom summary</summary>
  </entry>
</feed>"""


class TestRSSSource:
    @pytest.mark.asyncio
    @respx.mock
    async def test_parse_rss_feed(self):
        respx.get("https://feed.example.com/rss").respond(text=RSS_XML)
        src = RSSSource(name="test-rss", feed_url="https://feed.example.com/rss")
        candidates = await src.fetch_candidates(limit=10)
        assert len(candidates) == 2
        assert candidates[0].title == "Article One"
        assert candidates[0].url == "https://example.com/1"

    @pytest.mark.asyncio
    @respx.mock
    async def test_parse_atom_feed(self):
        respx.get("https://feed.example.com/atom").respond(text=ATOM_XML)
        src = RSSSource(name="test-atom", feed_url="https://feed.example.com/atom")
        candidates = await src.fetch_candidates(limit=10)
        assert len(candidates) == 1
        assert candidates[0].title == "Atom Entry"
        assert candidates[0].url == "https://example.com/atom/1"

    @pytest.mark.asyncio
    @respx.mock
    async def test_limit_respected(self):
        respx.get("https://feed.example.com/rss").respond(text=RSS_XML)
        src = RSSSource(name="test", feed_url="https://feed.example.com/rss")
        candidates = await src.fetch_candidates(limit=1)
        assert len(candidates) == 1

    def test_parse_invalid_xml(self):
        src = RSSSource(name="bad", feed_url="https://x.com")
        result = src._parse_feed("not xml at all <<<", limit=10)
        assert result == []

    def test_from_config(self):
        src = RSSSource.from_config({"name": "my-feed", "url": "https://x.com/rss"})
        assert src.name == "my-feed"
        assert src.feed_url == "https://x.com/rss"

    def test_source_name_set_on_candidates(self):
        src = RSSSource(name="tech-rss", feed_url="https://x.com")
        candidates = src._parse_feed(RSS_XML, limit=10)
        assert all(c.source_name == "tech-rss" for c in candidates)


# ── DuckDuckGo Search ──────────────────────────────────────────────


class TestSearchSource:
    @pytest.mark.asyncio
    async def test_fetch_with_mocked_ddgs(self, monkeypatch):
        from pipepost.sources.search import SearchSource

        class FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def text(self, query, max_results=5):
                return [
                    {"href": "https://example.com/1", "title": "Result 1", "body": "Body 1"},
                    {"href": "https://example.com/2", "title": "Result 2", "body": "Body 2"},
                ]

            def news(self, query, max_results=5):
                return []

        monkeypatch.setattr("pipepost.sources.search.DDGS", FakeDDGS, raising=False)
        # Patch at import location
        import pipepost.sources.search as search_mod
        original = None
        try:
            # The import is inside fetch_candidates, so we need to patch it in sys.modules
            import duckduckgo_search
            original = duckduckgo_search.DDGS
            duckduckgo_search.DDGS = FakeDDGS
        except ImportError:
            pytest.skip("duckduckgo_search not installed")

        try:
            src = SearchSource(queries=["test query"])
            candidates = await src.fetch_candidates(limit=5)
            assert len(candidates) == 2
            assert candidates[0].url == "https://example.com/1"
        finally:
            if original:
                duckduckgo_search.DDGS = original

    @pytest.mark.asyncio
    async def test_handles_search_exception(self, monkeypatch):
        from pipepost.sources.search import SearchSource

        class BrokenDDGS:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def text(self, query, max_results=5):
                raise RuntimeError("network error")

            def news(self, query, max_results=5):
                raise RuntimeError("also broken")

        try:
            import duckduckgo_search
            original = duckduckgo_search.DDGS
            duckduckgo_search.DDGS = BrokenDDGS
        except ImportError:
            pytest.skip("duckduckgo_search not installed")

        try:
            src = SearchSource(queries=["fail query"])
            candidates = await src.fetch_candidates(limit=5)
            assert candidates == []
        finally:
            duckduckgo_search.DDGS = original
