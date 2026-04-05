"""Scout step — fetch candidates from a source and populate the flow context."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipepost.core.registry import get_source, register_step
from pipepost.core.step import Step, StepBuildContext
from pipepost.exceptions import SourceError
from pipepost.metrics import metrics


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext

logger = logging.getLogger(__name__)


class ScoutStep(Step):
    """Fetch candidates from a registered source into the flow context."""

    name = "scout"

    def __init__(self, max_candidates: int = 30) -> None:
        self.max_candidates = max_candidates

    @classmethod
    def from_config(cls, build_ctx: StepBuildContext) -> ScoutStep:
        """Create from StepBuildContext."""
        return cls(max_candidates=build_ctx.max_candidates)

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if no source name is configured."""
        return not ctx.source_name

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Fetch candidates from the source and filter out existing URLs."""
        try:
            source = get_source(ctx.source_name)
        except KeyError as exc:
            raise SourceError(f"Unknown source: {ctx.source_name}") from exc

        try:
            raw_candidates = await source.fetch_candidates(limit=self.max_candidates)
        except SourceError:
            raise
        except Exception as exc:
            msg = f"Failed to fetch candidates from '{ctx.source_name}': {exc}"
            raise SourceError(msg) from exc

        filtered = [c for c in raw_candidates if c.url not in ctx.existing_urls]

        logger.info(
            "Scout: %d candidates fetched, %d after filtering (%d existing filtered out)",
            len(raw_candidates),
            len(filtered),
            len(raw_candidates) - len(filtered),
        )

        ctx.candidates = filtered
        metrics.record_candidates(ctx.source_name, len(filtered))

        if not filtered:
            ctx.add_error("No new candidates found")

        return ctx


register_step("scout", ScoutStep)
