"""Tests for FilterStep — keyword, domain, and title-length filtering."""

from __future__ import annotations

import pytest

from pipepost.core.context import Candidate, FlowContext
from pipepost.core.step import StepBuildContext
from pipepost.steps.filter import FilterStep


def _candidate(
    url: str = "https://example.com/article",
    title: str = "Example Article Title",
    snippet: str = "A short snippet about the article.",
) -> Candidate:
    return Candidate(url=url, title=title, snippet=snippet, source_name="test")


class TestKeywordsInclude:
    @pytest.mark.asyncio
    async def test_passes_when_keyword_in_title(self) -> None:
        step = FilterStep(keywords_include=["python"])
        ctx = FlowContext(candidates=[_candidate(title="Learn Python today")])
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 1

    @pytest.mark.asyncio
    async def test_passes_when_keyword_in_snippet(self) -> None:
        step = FilterStep(keywords_include=["python"])
        ctx = FlowContext(
            candidates=[_candidate(snippet="A guide to python programming")]
        )
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 1

    @pytest.mark.asyncio
    async def test_blocks_when_no_keyword_matches(self) -> None:
        step = FilterStep(keywords_include=["rust"])
        ctx = FlowContext(candidates=[_candidate(title="Learn Python today")])
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 0

    @pytest.mark.asyncio
    async def test_case_insensitive(self) -> None:
        step = FilterStep(keywords_include=["PYTHON"])
        ctx = FlowContext(candidates=[_candidate(title="Learn Python today")])
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 1


class TestKeywordsExclude:
    @pytest.mark.asyncio
    async def test_blocks_when_keyword_in_text(self) -> None:
        step = FilterStep(keywords_exclude=["spam"])
        ctx = FlowContext(candidates=[_candidate(title="Spam article")])
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 0

    @pytest.mark.asyncio
    async def test_passes_when_keyword_absent(self) -> None:
        step = FilterStep(keywords_exclude=["spam"])
        ctx = FlowContext(candidates=[_candidate(title="Good article")])
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 1

    @pytest.mark.asyncio
    async def test_case_insensitive(self) -> None:
        step = FilterStep(keywords_exclude=["SPAM"])
        ctx = FlowContext(candidates=[_candidate(snippet="contains Spam here")])
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 0


class TestDomainBlacklist:
    @pytest.mark.asyncio
    async def test_blocks_exact_domain(self) -> None:
        step = FilterStep(domain_blacklist=["reddit.com"])
        ctx = FlowContext(
            candidates=[_candidate(url="https://reddit.com/r/python/post")]
        )
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 0

    @pytest.mark.asyncio
    async def test_blocks_subdomain(self) -> None:
        step = FilterStep(domain_blacklist=["reddit.com"])
        ctx = FlowContext(
            candidates=[_candidate(url="https://old.reddit.com/r/python/post")]
        )
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 0

    @pytest.mark.asyncio
    async def test_passes_non_blocked_domain(self) -> None:
        step = FilterStep(domain_blacklist=["reddit.com"])
        ctx = FlowContext(
            candidates=[_candidate(url="https://example.com/article")]
        )
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 1

    @pytest.mark.asyncio
    async def test_case_insensitive(self) -> None:
        step = FilterStep(domain_blacklist=["Reddit.COM"])
        ctx = FlowContext(
            candidates=[_candidate(url="https://REDDIT.com/r/test")]
        )
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 0


class TestMinTitleLength:
    @pytest.mark.asyncio
    async def test_blocks_short_title(self) -> None:
        step = FilterStep(min_title_length=20)
        ctx = FlowContext(candidates=[_candidate(title="Short")])
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 0

    @pytest.mark.asyncio
    async def test_passes_long_enough_title(self) -> None:
        step = FilterStep(min_title_length=5)
        ctx = FlowContext(candidates=[_candidate(title="Long enough title")])
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 1

    @pytest.mark.asyncio
    async def test_zero_min_passes_everything(self) -> None:
        step = FilterStep(min_title_length=0)
        ctx = FlowContext(candidates=[_candidate(title="")])
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 1


class TestCombinedFilters:
    @pytest.mark.asyncio
    async def test_all_filters_applied(self) -> None:
        step = FilterStep(
            keywords_include=["python"],
            keywords_exclude=["spam"],
            domain_blacklist=["bad.com"],
            min_title_length=5,
        )
        candidates = [
            _candidate(title="Learn Python", url="https://good.com/1"),  # passes
            _candidate(title="Learn Python spam", url="https://good.com/2"),  # exclude
            _candidate(title="Learn Python", url="https://bad.com/3"),  # domain
            _candidate(title="Py", url="https://good.com/4"),  # too short + no kw
            _candidate(title="Learn Rust deeply", url="https://good.com/5"),  # no include kw
        ]
        ctx = FlowContext(candidates=candidates)
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 1
        assert ctx.candidates[0].url == "https://good.com/1"


class TestEmptyFilter:
    @pytest.mark.asyncio
    async def test_no_rules_passes_everything(self) -> None:
        step = FilterStep()
        candidates = [_candidate(), _candidate(title="Another")]
        ctx = FlowContext(candidates=candidates)
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 2


class TestAllFilteredOut:
    @pytest.mark.asyncio
    async def test_error_added_when_all_removed(self) -> None:
        step = FilterStep(keywords_include=["nonexistent"])
        ctx = FlowContext(candidates=[_candidate()])
        ctx = await step.execute(ctx)
        assert len(ctx.candidates) == 0
        assert ctx.has_errors
        assert "Filter removed all candidates" in ctx.errors[0]


class TestShouldSkip:
    def test_skips_on_empty_candidates(self) -> None:
        step = FilterStep()
        ctx = FlowContext(candidates=[])
        assert step.should_skip(ctx) is True

    def test_does_not_skip_with_candidates(self) -> None:
        step = FilterStep()
        ctx = FlowContext(candidates=[_candidate()])
        assert step.should_skip(ctx) is False


class TestFromConfig:
    def test_creates_from_build_context(self) -> None:
        build_ctx = StepBuildContext(
            filter_keywords_include=["ai", "ml"],
            filter_keywords_exclude=["spam"],
            filter_domain_blacklist=["bad.com"],
            filter_min_title_length=10,
        )
        step = FilterStep.from_config(build_ctx)
        assert step.keywords_include == ["ai", "ml"]
        assert step.keywords_exclude == ["spam"]
        assert step.domain_blacklist == ["bad.com"]
        assert step.min_title_length == 10

    def test_defaults_from_empty_build_context(self) -> None:
        build_ctx = StepBuildContext()
        step = FilterStep.from_config(build_ctx)
        assert step.keywords_include == []
        assert step.keywords_exclude == []
        assert step.domain_blacklist == []
        assert step.min_title_length == 0
