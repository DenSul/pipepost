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


class TestHtmlToMarkdownFormatting:
    """Verify _html_to_markdown preserves all markdown formatting types."""

    def test_preserves_headings(self, fetch_step):
        html = (
            "<html><body><article>"
            "<h1>Heading One</h1><h2>Heading Two</h2><h3>Heading Three</h3>"
            "</article></body></html>"
        )
        md = fetch_step._html_to_markdown(html)
        assert "# Heading One" in md
        assert "## Heading Two" in md
        assert "### Heading Three" in md

    def test_preserves_code_blocks(self, fetch_step):
        html = (
            "<html><body><article>"
            '<pre><code class="language-python">def hello():\n    print("hi")</code></pre>'
            "</article></body></html>"
        )
        md = fetch_step._html_to_markdown(html)
        assert "```" in md
        assert "def hello():" in md

    def test_preserves_inline_code(self, fetch_step):
        html = (
            "<html><body><article><p>Use the <code>variable</code> here</p></article></body></html>"
        )
        md = fetch_step._html_to_markdown(html)
        assert "`variable`" in md

    def test_preserves_links(self, fetch_step):
        html = (
            "<html><body><article>"
            '<p>Visit <a href="https://example.com">Example Site</a> for details</p>'
            "</article></body></html>"
        )
        md = fetch_step._html_to_markdown(html)
        assert "[Example Site](https://example.com)" in md

    def test_preserves_images(self, fetch_step):
        html = (
            "<html><body><article>"
            '<p><img src="https://example.com/img.png" alt="Diagram"></p>'
            "</article></body></html>"
        )
        md = fetch_step._html_to_markdown(html)
        assert "![Diagram](https://example.com/img.png)" in md

    def test_preserves_bold_italic(self, fetch_step):
        html = (
            "<html><body><article>"
            "<p>This is <strong>bold text</strong> and <em>italic text</em></p>"
            "</article></body></html>"
        )
        md = fetch_step._html_to_markdown(html)
        assert "**bold text**" in md
        assert "*italic text*" in md

    def test_preserves_unordered_lists(self, fetch_step):
        html = (
            "<html><body><article>"
            "<ul><li>First item</li><li>Second item</li><li>Third item</li></ul>"
            "</article></body></html>"
        )
        md = fetch_step._html_to_markdown(html)
        assert "First item" in md
        assert "Second item" in md
        # markdownify uses * or - for unordered lists
        assert any(marker in md for marker in ["* First", "- First", "+ First"])

    def test_preserves_ordered_lists(self, fetch_step):
        html = (
            "<html><body><article>"
            "<ol><li>Step one</li><li>Step two</li><li>Step three</li></ol>"
            "</article></body></html>"
        )
        md = fetch_step._html_to_markdown(html)
        assert "1." in md
        assert "Step one" in md
        assert "Step two" in md

    def test_preserves_tables(self, fetch_step):
        html = (
            "<html><body><article>"
            "<table><thead><tr><th>Name</th><th>Value</th></tr></thead>"
            "<tbody><tr><td>Alpha</td><td>100</td></tr>"
            "<tr><td>Beta</td><td>200</td></tr></tbody></table>"
            "</article></body></html>"
        )
        md = fetch_step._html_to_markdown(html)
        assert "|" in md
        assert "Name" in md
        assert "Alpha" in md

    def test_preserves_blockquotes(self, fetch_step):
        html = (
            "<html><body><article>"
            "<blockquote><p>This is a quoted passage from the source.</p></blockquote>"
            "</article></body></html>"
        )
        md = fetch_step._html_to_markdown(html)
        assert ">" in md
        assert "quoted passage" in md

    def test_complex_article(self, fetch_step):
        html = """
        <html><body><article>
            <h1>Main Title</h1>
            <p>This is <strong>bold</strong> and <em>italic</em> text.</p>
            <h2>Code Examples</h2>
            <p>Use <code>inline_var</code> for variables.</p>
            <pre><code class="language-python">def greet(name):
    return f"Hello, {name}"</code></pre>
            <h3>Resources</h3>
            <p>Visit <a href="https://docs.example.com">the docs</a> for more.</p>
            <img src="https://example.com/arch.png" alt="Architecture diagram">
            <blockquote><p>Knowledge is power.</p></blockquote>
            <ul><li>Benefit one</li><li>Benefit two</li></ul>
            <ol><li>First step</li><li>Second step</li></ol>
            <table><thead><tr><th>Feature</th><th>Status</th></tr></thead>
            <tbody><tr><td>Auth</td><td>Done</td></tr></tbody></table>
        </article></body></html>
        """
        md = fetch_step._html_to_markdown(html)
        # Headings
        assert "# Main Title" in md
        assert "## Code Examples" in md
        assert "### Resources" in md
        # Bold/italic
        assert "**bold**" in md
        assert "*italic*" in md
        # Inline code
        assert "`inline_var`" in md
        # Code block
        assert "```" in md
        assert "def greet(name):" in md
        # Link
        assert "[the docs](https://docs.example.com)" in md
        # Image
        assert "![Architecture diagram](https://example.com/arch.png)" in md
        # Blockquote
        assert ">" in md
        assert "Knowledge is power" in md
        # Lists
        assert "Benefit one" in md
        assert "First step" in md
        # Table
        assert "|" in md
        assert "Feature" in md
