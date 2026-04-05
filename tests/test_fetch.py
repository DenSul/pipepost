"""Tests for FetchStep — HTML fetching, markdown conversion, og:image."""

from __future__ import annotations

import pytest
import respx

from pipepost.core.context import Candidate, FlowContext
from pipepost.steps.fetch import FetchStep


# Ensure content is long enough (>200 chars after parsing)
_LONG_BODY = " ".join([f"Paragraph {i} with enough content to be meaningful." for i in range(30)])

SIMPLE_HTML = f"""
<!DOCTYPE html>
<html>
<head>
    <meta property="og:image" content="https://example.com/og.jpg">
</head>
<body>
    <article>
        <h1>Test Article</h1>
        <p>{_LONG_BODY}</p>
    </article>
    <script>evil();</script>
    <nav>Navigation stuff</nav>
</body>
</html>
"""

SHORT_HTML = """
<html><body><article><p>Too short.</p></article></body></html>
"""


@pytest.fixture
def fetch_step():
    return FetchStep(max_chars=20000)


@pytest.fixture
def ctx_with_candidates():
    return FlowContext(
        candidates=[
            Candidate(url="https://example.com/article-1", title="Article 1", score=100),
            Candidate(url="https://example.com/article-2", title="Article 2", score=50),
        ],
    )


class TestFetchStepExecute:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetches_first_candidate(self, fetch_step, ctx_with_candidates):
        respx.get("https://example.com/article-1").respond(text=SIMPLE_HTML)
        ctx = await fetch_step.execute(ctx_with_candidates)
        assert ctx.selected is not None
        assert ctx.selected.url == "https://example.com/article-1"

    @pytest.mark.asyncio
    @respx.mock
    async def test_skips_short_articles(self, fetch_step):
        ctx = FlowContext(
            candidates=[
                Candidate(url="https://short.com", title="Short"),
                Candidate(url="https://long.com", title="Long"),
            ],
        )
        respx.get("https://short.com").respond(text=SHORT_HTML)
        respx.get("https://long.com").respond(text=SIMPLE_HTML)
        result = await fetch_step.execute(ctx)
        assert result.selected is not None
        assert result.selected.url == "https://long.com"

    @pytest.mark.asyncio
    async def test_no_candidates_adds_error(self, fetch_step):
        ctx = FlowContext(candidates=[])
        result = await fetch_step.execute(ctx)
        assert result.has_errors
        assert "No candidates" in result.errors[0]

    @pytest.mark.asyncio
    @respx.mock
    async def test_skips_existing_urls(self, fetch_step):
        ctx = FlowContext(
            candidates=[
                Candidate(url="https://seen.com", title="Seen"),
                Candidate(url="https://new.com", title="New"),
            ],
            existing_urls={"https://seen.com"},
        )
        respx.get("https://new.com").respond(text=SIMPLE_HTML)
        result = await fetch_step.execute(ctx)
        assert result.selected is not None
        assert result.selected.url == "https://new.com"

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_candidates_fail(self, fetch_step):
        ctx = FlowContext(
            candidates=[Candidate(url="https://dead.com", title="Dead")],
        )
        respx.get("https://dead.com").respond(status_code=500)
        result = await fetch_step.execute(ctx)
        assert result.has_errors
        assert "unfetchable" in result.errors[0]


class TestOgImageExtraction:
    @pytest.mark.asyncio
    @respx.mock
    async def test_extracts_og_image(self, fetch_step, ctx_with_candidates):
        respx.get("https://example.com/article-1").respond(text=SIMPLE_HTML)
        ctx = await fetch_step.execute(ctx_with_candidates)
        assert ctx.selected is not None
        assert ctx.selected.cover_image == "https://example.com/og.jpg"

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_og_image_returns_none(self, fetch_step):
        html_no_og = "<html><body><article>" + f"<p>{_LONG_BODY}</p>" + "</article></body></html>"
        ctx = FlowContext(
            candidates=[Candidate(url="https://no-og.com", title="No OG")],
        )
        respx.get("https://no-og.com").respond(text=html_no_og)
        result = await fetch_step.execute(ctx)
        assert result.selected is not None
        assert result.selected.cover_image is None


class TestHtmlToMarkdown:
    def test_strips_script_and_nav(self, fetch_step):
        html = (
            "<html><body><script>x</script><nav>n</nav>"
            "<article><p>content</p></article></body></html>"
        )
        md = fetch_step._html_to_markdown(html)
        assert "content" in md

    def test_respects_max_chars(self):
        step = FetchStep(max_chars=50)
        html = "<html><body><article>" + "a" * 200 + "</article></body></html>"
        md = step._html_to_markdown(html)
        assert len(md) <= 50

    def test_prefers_article_tag(self, fetch_step):
        html = "<html><body><div>noise</div><article><p>real content</p></article></body></html>"
        md = fetch_step._html_to_markdown(html)
        assert "real content" in md
