"""Tests for QualityGateStep."""

from __future__ import annotations

import pytest

from pipepost.core.context import Article, FlowContext
from pipepost.core.step import StepBuildContext
from pipepost.steps.quality_gate import QualityGateStep


@pytest.fixture()
def step() -> QualityGateStep:
    return QualityGateStep(
        min_content_len=100,
        min_paragraphs=2,
        max_boilerplate_ratio=0.4,
        max_code_ratio=0.7,
        min_unique_words=20,
    )


def _make_ctx(content: str, title: str = "Test Article") -> FlowContext:
    ctx = FlowContext(source_name="test")
    ctx.selected = Article(url="https://example.com/test", title=title, content=content)
    return ctx


GOOD_CONTENT = (
    "This is the first paragraph of a well-written article about technology. "
    "It contains meaningful insights about software development and engineering practices.\n\n"
    "The second paragraph explores the implications of modern frameworks. "
    "There are many unique words here to satisfy the vocabulary threshold. "
    "Innovation drives progress in the industry.\n\n"
    "Finally, the third paragraph wraps up with concrete conclusions about future trends."
)


class TestQualityGatePass:
    """Test articles that should pass quality gate."""

    @pytest.mark.asyncio()
    async def test_good_article_passes(self, step: QualityGateStep) -> None:
        ctx = _make_ctx(GOOD_CONTENT)
        result = await step.execute(ctx)
        assert result.selected is not None
        assert not result.has_errors

    @pytest.mark.asyncio()
    async def test_preserves_article_on_pass(self, step: QualityGateStep) -> None:
        ctx = _make_ctx(GOOD_CONTENT)
        original_url = ctx.selected.url
        result = await step.execute(ctx)
        assert result.selected is not None
        assert result.selected.url == original_url


class TestQualityGateReject:
    """Test articles that should be rejected."""

    @pytest.mark.asyncio()
    async def test_too_short(self, step: QualityGateStep) -> None:
        ctx = _make_ctx("Short text.\n\nAnother short line.")
        result = await step.execute(ctx)
        assert result.selected is None
        assert any("too short" in e.lower() for e in result.errors)

    @pytest.mark.asyncio()
    async def test_too_few_paragraphs(self, step: QualityGateStep) -> None:
        step_strict = QualityGateStep(
            min_content_len=10,
            min_paragraphs=5,
            min_unique_words=5,
        )
        ctx = _make_ctx("One big paragraph with enough words to pass length check. " * 10)
        result = await step_strict.execute(ctx)
        assert result.selected is None
        assert any("paragraphs" in e.lower() for e in result.errors)

    @pytest.mark.asyncio()
    async def test_too_much_boilerplate(self, step: QualityGateStep) -> None:
        boilerplate = "\n".join([
            "Subscribe to our newsletter",
            "Sign up for our mailing list",
            "Cookie policy agreement",
            "Privacy policy",
            "Share this on Twitter",
            "Related articles",
            "You may also like",
            "Advertisement",
            "Sponsored content",
            "Terms of service",
        ])
        content = f"One good line of content.\n\nAnother good line.\n\n{boilerplate}"
        ctx = _make_ctx(content)
        result = await step.execute(ctx)
        assert result.selected is None
        assert any("boilerplate" in e.lower() for e in result.errors)

    @pytest.mark.asyncio()
    async def test_too_much_code(self) -> None:
        step = QualityGateStep(
            min_content_len=10,
            min_paragraphs=1,
            max_code_ratio=0.3,
            min_unique_words=5,
        )
        code = "```python\n" + "x = 1\n" * 50 + "```"
        content = f"Brief intro.\n\n{code}"
        ctx = _make_ctx(content)
        result = await step.execute(ctx)
        assert result.selected is None
        assert any("code ratio" in e.lower() for e in result.errors)

    @pytest.mark.asyncio()
    async def test_too_few_unique_words(self) -> None:
        step = QualityGateStep(
            min_content_len=10,
            min_paragraphs=1,
            min_unique_words=100,
        )
        content = "same word same word same word.\n\nsame word same word."
        ctx = _make_ctx(content)
        result = await step.execute(ctx)
        assert result.selected is None
        assert any("unique words" in e.lower() for e in result.errors)


class TestQualityGateShouldSkip:
    """Test should_skip."""

    def test_skip_when_no_article(self, step: QualityGateStep) -> None:
        ctx = FlowContext(source_name="test")
        assert step.should_skip(ctx) is True

    def test_no_skip_with_article(self, step: QualityGateStep) -> None:
        ctx = _make_ctx(GOOD_CONTENT)
        assert step.should_skip(ctx) is False


class TestQualityGateFromConfig:
    """Test from_config."""

    def test_defaults(self) -> None:
        build_ctx = StepBuildContext()
        step = QualityGateStep.from_config(build_ctx)
        assert step.min_content_len == 500
        assert step.min_paragraphs == 3
        assert step.max_boilerplate_ratio == 0.4
        assert step.max_code_ratio == 0.7
        assert step.min_unique_words == 50

    def test_custom(self) -> None:
        build_ctx = StepBuildContext(
            qg_min_content_len=1000,
            qg_min_paragraphs=5,
            qg_max_boilerplate_ratio=0.2,
            qg_max_code_ratio=0.5,
            qg_min_unique_words=100,
        )
        step = QualityGateStep.from_config(build_ctx)
        assert step.min_content_len == 1000
        assert step.min_paragraphs == 5
        assert step.max_boilerplate_ratio == 0.2
        assert step.max_code_ratio == 0.5
        assert step.min_unique_words == 100


class TestQualityGateEmptyContext:
    """Test edge case — no selected article."""

    @pytest.mark.asyncio()
    async def test_adds_error(self, step: QualityGateStep) -> None:
        ctx = FlowContext(source_name="test")
        result = await step.execute(ctx)
        assert "No article for quality check" in result.errors


class TestBoilerplateStrip:
    """Test _strip_boilerplate internals."""

    def test_removes_boilerplate_lines(self, step: QualityGateStep) -> None:
        content = "Good content here.\nSubscribe to our newsletter\nMore good stuff."
        clean, ratio = step._strip_boilerplate(content)
        assert "Subscribe" not in clean
        assert "Good content" in clean
        assert ratio > 0

    def test_clean_content_ratio_zero(self, step: QualityGateStep) -> None:
        content = "All clean content.\nNo boilerplate here.\nJust good stuff."
        _, ratio = step._strip_boilerplate(content)
        assert ratio == 0.0


class TestCodeRatio:
    """Test _code_ratio internals."""

    def test_no_code(self, step: QualityGateStep) -> None:
        assert step._code_ratio("Just text, no code blocks.") == 0.0

    def test_all_code(self, step: QualityGateStep) -> None:
        content = "```python\nprint('hello')\n```"
        assert step._code_ratio(content) == 1.0

    def test_mixed(self, step: QualityGateStep) -> None:
        content = "Some text.\n```\ncode\n```\nMore text."
        ratio = step._code_ratio(content)
        assert 0 < ratio < 1
