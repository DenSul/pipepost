"""Integration smoke tests — exercise real network sources and the scout-fetch pipeline.

These tests hit live APIs and are skipped when PIPEPOST_SKIP_INTEGRATION=1.
Run explicitly with: pytest tests/test_integration.py -v
"""

from __future__ import annotations

import os

import pytest

from pipepost.core.context import FlowContext
from pipepost.sources.hackernews import HackerNewsSource
from pipepost.sources.rss import RSSSource
from pipepost.steps.fetch import FetchStep


pytestmark = pytest.mark.integration

_SKIP = pytest.mark.skipif(
    os.environ.get("PIPEPOST_SKIP_INTEGRATION") == "1",
    reason="Integration tests disabled via PIPEPOST_SKIP_INTEGRATION=1",
)

_BBC_TECH_FEED = "https://feeds.bbci.co.uk/news/technology/rss.xml"


def _skip_on_network_error(func):
    """Decorator: convert network errors into pytest.skip so CI stays green."""

    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            network_keywords = ("timeout", "connect", "resolve", "network", "DNS", "SSLError")
            msg = str(exc)
            if any(kw.lower() in msg.lower() for kw in network_keywords):
                pytest.skip(f"Network unavailable: {exc}")
            raise

    return wrapper


# ── RSS Source ────────────────────────────────────────────────────────


class TestRSSIntegration:
    @_SKIP
    @_skip_on_network_error
    async def test_rss_fetch_candidates(self):
        """Fetch real BBC Tech RSS feed and verify candidates."""
        src = RSSSource(name="bbc-tech", feed_url=_BBC_TECH_FEED)
        candidates = await src.fetch_candidates(limit=3)

        assert len(candidates) > 0, "Expected at least one candidate from BBC feed"
        for c in candidates:
            assert c.url, "Candidate must have a URL"
            assert c.title, "Candidate must have a title"
            assert c.source_name == "bbc-tech"


# ── HackerNews Source ─────────────────────────────────────────────────


class TestHackerNewsIntegration:
    @_SKIP
    @_skip_on_network_error
    async def test_hackernews_fetch_candidates(self):
        """Fetch real HN top stories with a low min_score."""
        src = HackerNewsSource(min_score=1)
        candidates = await src.fetch_candidates(limit=3)

        assert len(candidates) > 0, "Expected at least one HN candidate"
        for c in candidates:
            assert c.url, "Candidate must have a URL"
            assert c.title, "Candidate must have a title"
            assert c.source_name == "hackernews"
            assert c.score >= 1


# ── Mini Pipeline: Scout (RSS) -> Fetch ──────────────────────────────


class TestMiniPipelineIntegration:
    @_SKIP
    @_skip_on_network_error
    async def test_rss_scout_then_fetch(self):
        """End-to-end: RSS candidates -> fetch one article content."""
        # Step 1: Scout — get candidates from BBC Tech
        src = RSSSource(name="bbc-tech", feed_url=_BBC_TECH_FEED)
        candidates = await src.fetch_candidates(limit=5)
        assert len(candidates) > 0, "Scout must return candidates"

        # Step 2: Build a FlowContext with those candidates
        ctx = FlowContext(
            candidates=candidates,
            source_name="bbc-tech",
            target_lang="en",
        )

        # Step 3: Fetch — download one article
        fetch = FetchStep(max_chars=5000, timeout=20.0)
        ctx = await fetch.execute(ctx)

        # We do NOT assert ctx.selected is not None because some BBC pages
        # may be too short after extraction.  Instead, verify no crash and
        # that the step either selected an article or recorded a reason.
        if ctx.selected is not None:
            assert ctx.selected.url, "Fetched article must have a URL"
            assert ctx.selected.content, "Fetched article must have content"
            assert len(ctx.selected.content) > 0
        else:
            # All candidates were unfetchable — acceptable in integration
            assert ctx.has_errors, "If no article selected, errors should be recorded"
