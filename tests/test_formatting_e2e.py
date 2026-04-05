"""End-to-end test: markdown formatting survives the full pipeline."""

from __future__ import annotations

import re

import pytest

from pipepost.steps.fetch import FetchStep
from pipepost.steps.translate import TranslateStep


def count_formatting(text):
    """Count markdown formatting elements in text."""
    return {
        "headings": len(re.findall(r"^#{1,6} ", text, re.MULTILINE)),
        "code_blocks": text.count("```"),
        "inline_code": len(re.findall(r"`[^`\n]+`", text)),
        "links": len(re.findall(r"\[([^\]]+)\]\(http", text)),
        "images": len(re.findall(r"!\[", text)),
        "bold": len(re.findall(r"\*\*[^*]+\*\*", text)),
        "lists": len(re.findall(r"^[*\-] ", text, re.MULTILINE)),
        "table_rows": len(re.findall(r"^\|", text, re.MULTILINE)),
    }


# Rich HTML article with every formatting type
_RICH_HTML = """
<html>
<body>
<article>
    <h1>Understanding Modern Architecture</h1>
    <p>This guide covers <strong>essential patterns</strong> and <em>best practices</em>
    for building scalable systems.</p>

    <h2>Code Examples</h2>
    <p>Initialize with <code>config.init()</code> before calling other methods.</p>
    <pre><code class="language-python">class Pipeline:
    def __init__(self, steps):
        self.steps = steps

    async def run(self):
        for step in self.steps:
            await step.execute()</code></pre>

    <h3>External Resources</h3>
    <p>Read the <a href="https://docs.example.com/guide">official guide</a> and
    the <a href="https://blog.example.com/tips">tips article</a>.</p>

    <img src="https://example.com/architecture.png" alt="System architecture overview">
    <img src="https://example.com/flow.png" alt="Data flow diagram">

    <blockquote><p>Good architecture is about trade-offs, not perfection.</p></blockquote>

    <ul>
        <li>Separation of concerns</li>
        <li>Dependency injection</li>
        <li>Event-driven design</li>
    </ul>

    <ol>
        <li>Define interfaces</li>
        <li>Implement adapters</li>
        <li>Wire everything together</li>
    </ol>

    <table>
        <thead><tr><th>Pattern</th><th>Use Case</th><th>Complexity</th></tr></thead>
        <tbody>
            <tr><td>Pipeline</td><td>Data processing</td><td>Low</td></tr>
            <tr><td>Event Sourcing</td><td>Audit trails</td><td>High</td></tr>
        </tbody>
    </table>
</article>
</body>
</html>
"""


class TestFormattingE2E:
    """End-to-end: HTML → markdown → prompt → mock LLM → parse → verify formatting."""

    @pytest.fixture
    def fetch_step(self):
        return FetchStep(max_chars=50000)

    @pytest.fixture
    def translate_step(self):
        return TranslateStep(model="test-model", target_lang="ru")

    def test_formatting_survives_full_pipeline(self, fetch_step, translate_step):
        # Step 1: HTML → markdown
        markdown = fetch_step._html_to_markdown(_RICH_HTML)

        # Verify markdown has formatting
        md_counts = count_formatting(markdown)
        assert md_counts["headings"] >= 3, f"Expected >=3 headings, got {md_counts['headings']}"
        assert md_counts["code_blocks"] >= 2, (
            f"Expected >=2 code fences, got {md_counts['code_blocks']}"
        )
        assert md_counts["links"] >= 2, f"Expected >=2 links, got {md_counts['links']}"
        assert md_counts["images"] >= 1, f"Expected >=1 image, got {md_counts['images']}"
        assert md_counts["bold"] >= 1, f"Expected >=1 bold, got {md_counts['bold']}"

        # Step 2: markdown → prompt
        prompt = translate_step._build_prompt("Understanding Modern Architecture", markdown)
        assert markdown[:200] in prompt  # content is embedded in prompt

        # Step 3: simulate LLM response (echo content as-is, wrapped in markers)
        mock_llm_response = (
            "===TITLE_RU===\n"
            "Понимание современной архитектуры\n"
            f"===CONTENT_RU===\n{markdown}\n"
            "===TAGS===\n"
            "architecture, python, patterns\n"
        )

        # Step 4: parse LLM response
        parsed = translate_step._parse_output(mock_llm_response)
        assert parsed is not None
        final_content = parsed["content_translated"]

        # Step 5: verify all formatting survived
        final_counts = count_formatting(final_content)

        assert final_counts["headings"] >= 3, (
            f"Headings lost: {md_counts['headings']} → {final_counts['headings']}"
        )
        assert final_counts["code_blocks"] >= 2, (
            f"Code blocks lost: {md_counts['code_blocks']} → {final_counts['code_blocks']}"
        )
        assert final_counts["inline_code"] >= 1, (
            f"Inline code lost: {md_counts['inline_code']} → {final_counts['inline_code']}"
        )
        assert final_counts["links"] >= 2, (
            f"Links lost: {md_counts['links']} → {final_counts['links']}"
        )
        assert final_counts["images"] >= 1, (
            f"Images lost: {md_counts['images']} → {final_counts['images']}"
        )
        assert final_counts["bold"] >= 1, f"Bold lost: {md_counts['bold']} → {final_counts['bold']}"
        assert final_counts["lists"] >= 1, (
            f"Lists lost: {md_counts['lists']} → {final_counts['lists']}"
        )
        assert final_counts["table_rows"] >= 1, (
            f"Table rows lost: {md_counts['table_rows']} → {final_counts['table_rows']}"
        )

        # Counts should be identical (no formatting was added or removed)
        assert final_counts == md_counts, (
            f"Formatting counts changed:\n  Before: {md_counts}\n  After:  {final_counts}"
        )
