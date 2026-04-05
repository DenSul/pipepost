"""Filter candidates by keywords, domains, and title length."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from pipepost.core.registry import register_step
from pipepost.core.step import Step, StepBuildContext


if TYPE_CHECKING:
    from pipepost.core.context import Candidate, FlowContext

logger = logging.getLogger(__name__)


class FilterStep(Step):
    """Filter candidates by keywords, domain blacklist, and title length."""

    name = "filter"

    def __init__(
        self,
        keywords_include: list[str] | None = None,
        keywords_exclude: list[str] | None = None,
        domain_blacklist: list[str] | None = None,
        min_title_length: int = 0,
    ) -> None:
        self.keywords_include = [k.lower() for k in (keywords_include or [])]
        self.keywords_exclude = [k.lower() for k in (keywords_exclude or [])]
        self.domain_blacklist = [d.lower() for d in (domain_blacklist or [])]
        self.min_title_length = min_title_length

    @classmethod
    def from_config(cls, build_ctx: StepBuildContext) -> FilterStep:
        """Create from StepBuildContext."""
        return cls(
            keywords_include=build_ctx.filter_keywords_include,
            keywords_exclude=build_ctx.filter_keywords_exclude,
            domain_blacklist=build_ctx.filter_domain_blacklist,
            min_title_length=build_ctx.filter_min_title_length,
        )

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if no candidates to filter."""
        return not ctx.candidates

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Filter candidates based on configured rules."""
        before = len(ctx.candidates)
        filtered = [c for c in ctx.candidates if self._passes(c)]

        removed = before - len(filtered)
        if removed:
            logger.info("Filter: removed %d/%d candidates", removed, before)

        ctx.candidates = filtered

        if not filtered:
            ctx.add_error("Filter removed all candidates — none match criteria")

        return ctx

    def _passes(self, candidate: Candidate) -> bool:
        """Check if a candidate passes all filter rules."""
        text = f"{candidate.title} {candidate.snippet}".lower()

        # Domain blacklist
        if self.domain_blacklist:
            domain = urlparse(candidate.url).netloc.lower()
            if any(blocked in domain for blocked in self.domain_blacklist):
                return False

        # Keywords exclude (blacklist)
        if self.keywords_exclude and any(kw in text for kw in self.keywords_exclude):
            return False

        # Keywords include (whitelist) — at least one must match
        if self.keywords_include and not any(kw in text for kw in self.keywords_include):
            return False

        # Min title length
        return not (self.min_title_length > 0 and len(candidate.title) < self.min_title_length)


register_step("filter", FilterStep)
